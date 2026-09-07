from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .models import (
    Appointment,
    AuditEvent,
    Doctor,
    Holiday,
    LookupOption,
    Patient,
    QueueToken,
    ScheduleSlot,
)
from .notification import SmsService
from .schemas import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentUpdate,
    PatientCreate,
    PatientRead,
    SlotCreate,
    TokenCreate,
    TokenRead,
)
from .service import QueueService


class AppointmentService:
    def __init__(self, db: Session):
        self.db = db

    def patients(self, query: str | None) -> list[PatientRead]:
        stmt = select(Patient)
        if query:
            value = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(Patient.patient_number.ilike(value), Patient.mobile.ilike(value), Patient.name.ilike(value))
            )
        return [PatientRead.model_validate(item) for item in self.db.scalars(stmt.order_by(Patient.name).limit(100))]

    def create_patient(self, payload: PatientCreate, actor: str) -> PatientRead:
        for category, value in (("patient_title", payload.title), ("sex", payload.sex)):
            if value and not self.db.scalar(
                select(LookupOption.id).where(
                    LookupOption.category == category, LookupOption.value == value, LookupOption.is_active.is_(True)
                )
            ):
                configured = self.db.scalar(select(LookupOption.id).where(LookupOption.category == category))
                if configured:
                    raise HTTPException(422, f"Invalid or inactive {category.replace('_', ' ')}")
        number = payload.patient_number or f"CMH-{date.today():%y%m%d}-{uuid4().hex[:8].upper()}"
        if self.db.scalar(select(Patient).where(Patient.patient_number == number)):
            raise HTTPException(409, "Patient number already exists")
        patient = Patient(**payload.model_dump(exclude={"patient_number"}), patient_number=number)
        self.db.add(patient)
        self.db.flush()
        self.db.add(
            AuditEvent(
                action="patient.created", actor=actor, detail={"patient_id": patient.id, "patient_number": number}
            )
        )
        self.db.commit()
        self.db.refresh(patient)
        return PatientRead.model_validate(patient)

    def slots(self, doctor_id: str | None = None, slot_date: date | None = None) -> list[ScheduleSlot]:
        stmt = select(ScheduleSlot).where(ScheduleSlot.is_active.is_(True))
        if doctor_id:
            stmt = stmt.where(ScheduleSlot.doctor_id == doctor_id)
        if slot_date:
            stmt = stmt.where(func.date(ScheduleSlot.starts_at) == slot_date)
        return list(self.db.scalars(stmt.order_by(ScheduleSlot.starts_at).limit(500)))

    def create_slot(self, payload: SlotCreate, actor: str) -> ScheduleSlot:
        doctor = self.db.scalar(select(Doctor).where(Doctor.id == payload.doctor_id).with_for_update())
        if not doctor or not doctor.is_active:
            raise HTTPException(404, "Doctor not found or inactive")
        if payload.ends_at <= payload.starts_at:
            raise HTTPException(422, "Slot end time must be after its start time")
        if payload.starts_at <= datetime.utcnow():
            raise HTTPException(422, "Slot start time must be in the future")
        if self.db.scalar(
            select(ScheduleSlot.id).where(
                ScheduleSlot.doctor_id == payload.doctor_id,
                ScheduleSlot.starts_at < payload.ends_at,
                ScheduleSlot.ends_at > payload.starts_at,
                ScheduleSlot.is_active.is_(True),
            )
        ):
            raise HTTPException(409, "This slot overlaps an existing active slot")
        slot = ScheduleSlot(**payload.model_dump(), is_active=True)
        self.db.add(slot)
        self.db.flush()
        self.db.add(
            AuditEvent(
                action="schedule.slot_created",
                actor=actor,
                detail={"slot_id": slot.id, "doctor_id": slot.doctor_id, "starts_at": slot.starts_at.isoformat()},
            )
        )
        self.db.commit()
        self.db.refresh(slot)
        return slot

    def appointments(self, doctor_id: str | None = None, status: str | None = None) -> list[AppointmentRead]:
        stmt = select(Appointment)
        if doctor_id:
            stmt = stmt.where(Appointment.doctor_id == doctor_id)
        if status:
            stmt = stmt.where(Appointment.status == status)
        return [
            AppointmentRead.model_validate(item)
            for item in self.db.scalars(stmt.order_by(Appointment.created_at.desc()).limit(500))
        ]

    def create_appointment(self, payload: AppointmentCreate, actor: str) -> AppointmentRead:
        patient = self.db.get(Patient, payload.patient_id)
        doctor = self.db.get(Doctor, payload.doctor_id)
        slot = self.db.scalar(select(ScheduleSlot).where(ScheduleSlot.id == payload.slot_id).with_for_update())
        if not patient:
            raise HTTPException(404, "Patient not found")
        if not doctor or not doctor.is_active:
            raise HTTPException(404, "Doctor not found or inactive")
        if payload.reason:
            reason = self.db.scalar(
                select(LookupOption.id).where(
                    LookupOption.category == "appointment_reason",
                    LookupOption.value == payload.reason,
                    LookupOption.is_active.is_(True),
                )
            )
            if not reason and self.db.scalar(
                select(LookupOption.id).where(LookupOption.category == "appointment_reason")
            ):
                raise HTTPException(422, "Invalid or inactive appointment reason")
        self._validate_slot(slot, doctor.id)
        self._assert_not_holiday(slot)
        self._assert_capacity(slot)
        appointment = Appointment(
            **payload.model_dump(),
            appointment_number=f"APT-{date.today():%y%m%d}-{uuid4().hex[:8].upper()}",
            status="scheduled",
            created_by=actor,
        )
        self.db.add(appointment)
        self.db.flush()
        self._audit(appointment, "appointment.created", actor, detail={"status": "scheduled"})
        sms = SmsService(self.db)
        sms.queue(
            patient.mobile,
            "appointment_confirmation",
            f"CMH appointment {appointment.appointment_number}: {doctor.name}, "
            f"{slot.starts_at:%d %b %Y %I:%M %p}, room {doctor.room_number}.",
        )
        self.db.commit()
        return AppointmentRead.model_validate(appointment)

    def update_appointment(self, appointment_id: str, payload: AppointmentUpdate, actor: str) -> AppointmentRead:
        appointment = self._get(appointment_id)
        previous = appointment.status
        if payload.action == "confirm":
            if previous != "scheduled":
                raise HTTPException(409, "Only scheduled appointments can be confirmed")
            appointment.status = "confirmed"
        elif payload.action == "cancel":
            if previous in {"cancelled", "checked_in", "completed"}:
                raise HTTPException(409, "This appointment cannot be cancelled")
            appointment.status = "cancelled"
        else:
            if previous not in {"scheduled", "confirmed"} or not payload.slot_id:
                raise HTTPException(409, "Only active appointments can be rescheduled to a slot")
            slot = self.db.scalar(select(ScheduleSlot).where(ScheduleSlot.id == payload.slot_id).with_for_update())
            self._validate_slot(slot, appointment.doctor_id)
            self._assert_not_holiday(slot)
            self._assert_capacity(slot, exclude_id=appointment.id)
            appointment.slot_id = slot.id
        appointment.reason = payload.reason
        self._audit(
            appointment,
            f"appointment.{payload.action}",
            actor,
            reason=payload.reason,
            detail={"previous_status": previous, "new_status": appointment.status, "slot_id": appointment.slot_id},
        )
        self.db.commit()
        return AppointmentRead.model_validate(appointment)

    def check_in(self, appointment_id: str, actor: str) -> TokenRead:
        appointment = self._get(appointment_id)
        existing = self.db.scalar(select(QueueToken).where(QueueToken.appointment_id == appointment.id))
        if existing:
            return QueueService._read(existing)
        if appointment.status not in {"scheduled", "confirmed"}:
            raise HTTPException(409, "Only scheduled or confirmed appointments can be checked in")
        patient = self.db.get(Patient, appointment.patient_id)
        doctor = self.db.get(Doctor, appointment.doctor_id)
        slot = self.db.get(ScheduleSlot, appointment.slot_id)
        token = QueueService(self.db).create_token(
            TokenCreate(
                patient_title=patient.title,
                patient_name=patient.name,
                patient_phone=patient.mobile,
                doctor_id=doctor.id,
                doctor_name=doctor.name,
                department=doctor.department,
                room_number=doctor.room_number,
                source="appointment",
                patient_id=patient.id,
                appointment_id=appointment.id,
                scheduled_at=slot.starts_at,
            ),
            actor,
        )
        appointment.status = "checked_in"
        appointment.checked_in_at = datetime.utcnow()
        self._audit(appointment, "appointment.checked_in", actor, detail={"token_id": token.id})
        sms = SmsService(self.db)
        estimated = max(token.waiting_minutes, 0)
        sms.queue(
            patient.mobile,
            "token_confirmation",
            f"CMH token {token.token_number}. {doctor.name}, room {doctor.room_number}. "
            f"Estimated wait {estimated} minutes.",
        )
        self.db.commit()
        return token

    def _assert_capacity(self, slot: ScheduleSlot, exclude_id: str | None = None) -> None:
        stmt = select(func.count(Appointment.id)).where(
            Appointment.slot_id == slot.id, Appointment.status != "cancelled"
        )
        if exclude_id:
            stmt = stmt.where(Appointment.id != exclude_id)
        if self.db.scalar(stmt) >= slot.capacity:
            raise HTTPException(409, "The selected slot is full")

    def _assert_not_holiday(self, slot: ScheduleSlot) -> None:
        holiday = self.db.scalar(
            select(Holiday).where(Holiday.holiday_date == slot.starts_at.date(), Holiday.is_active.is_(True))
        )
        if holiday:
            raise HTTPException(409, f"Appointments are closed for {holiday.name}")

    @staticmethod
    def _validate_slot(slot: ScheduleSlot | None, doctor_id: str) -> None:
        if not slot or not slot.is_active or slot.doctor_id != doctor_id:
            raise HTTPException(422, "The selected slot is not available for this doctor")
        if slot.ends_at <= slot.starts_at:
            raise HTTPException(422, "Slot end time must be after its start time")

    def _get(self, appointment_id: str) -> Appointment:
        appointment = self.db.get(Appointment, appointment_id)
        if not appointment:
            raise HTTPException(404, "Appointment not found")
        return appointment

    def _audit(
        self,
        appointment: Appointment,
        action: str,
        actor: str,
        *,
        reason: str | None = None,
        detail: dict | None = None,
    ) -> None:
        self.db.add(
            AuditEvent(
                action=action,
                actor=actor,
                reason=reason,
                detail={
                    "appointment_id": appointment.id,
                    "appointment_number": appointment.appointment_number,
                    **(detail or {}),
                },
            )
        )
