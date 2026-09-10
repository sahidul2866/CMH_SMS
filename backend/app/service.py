from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    AppSetting,
    AuditEvent,
    CallEvent,
    Doctor,
    LookupOption,
    QueueControl,
    QueueToken,
    RegistrationCounter,
    WaitingRoom,
)
from .schemas import DisplayRead, TokenCreate, TokenRead

ACTIVE_STATUSES = ("waiting", "called")
PRIORITY_WEIGHT = {
    "emergency": 0,
    "urgent": 1,
    "pregnant": 2,
    "disabled": 3,
    "elderly": 4,
    "vip": 5,
    "priority": 5,
    "follow_up": 6,
    "normal": 10,
}


class QueueService:
    def __init__(self, db: Session):
        self.db = db

    def create_token(self, payload: TokenCreate, actor: str = "reception.operator") -> TokenRead:
        from .registration import validate_registration
        validate_registration(self.db, payload)
        self._require_lookup("service_category", payload.service_category)
        self._require_lookup("priority_category", payload.priority)
        if payload.patient_title:
            self._require_lookup("designation", payload.patient_title)
        if payload.rank:
            designation = self._require_lookup("rank_relationship", payload.rank)
            if (designation.metadata_json or {}).get("priority") == "vip" or payload.rank.lower() == "vip":
                payload = payload.model_copy(update={"priority": "vip"})
        if payload.patient_source:
            self._require_lookup("patient_source", payload.patient_source)
        doctor = self.db.scalar(select(Doctor).where(Doctor.id == payload.doctor_id).with_for_update()) if payload.doctor_id else None
        if payload.doctor_id and (not doctor or not doctor.is_active):
            raise HTTPException(404, "Doctor not found or inactive")
        sequence = (
            self.db.scalar(
                select(func.coalesce(func.max(QueueToken.sequence), 0)).where(
                    QueueToken.token_date == date.today(), QueueToken.doctor_id == payload.doctor_id
                )
            )
            + 1
        )
        room = self.db.get(WaitingRoom, doctor.waiting_room_id) if doctor else None
        if doctor and (not room or not room.is_active):
            raise HTTPException(409, "Doctor has no active waiting room")
        from .monthly_report import classify

        values = payload.model_dump()
        values["summary_category"] = classify(self.db, payload)
        # Reception registrations join the shared pool. Explicit appointment assignments remain supported.
        values.update(doctor_id=doctor.id if doctor else None,
            doctor_name=doctor.name if doctor else "", department=doctor.department if doctor else "",
            room_number=doctor.room_number if doctor else "", waiting_room=room.code if room else payload.waiting_room)
        if not doctor and payload.waiting_room:
            waiting_area = self.db.scalar(select(WaitingRoom).where(WaitingRoom.code == payload.waiting_room, WaitingRoom.is_active.is_(True)))
            if not waiting_area:
                raise HTTPException(422, "Unknown waiting area")
        year = date.today().year
        if not self.db.get(RegistrationCounter, year):
            try:
                with self.db.begin_nested():
                    self.db.add(RegistrationCounter(year=year, sequence=0))
                    self.db.flush()
            except IntegrityError:
                pass  # Another registration initialized this year concurrently.
        self.db.execute(update(RegistrationCounter).where(RegistrationCounter.year == year).values(
            sequence=RegistrationCounter.sequence + 1
        ))
        annual_sequence = self.db.scalar(select(RegistrationCounter.sequence).where(RegistrationCounter.year == year))
        token = QueueToken(
            serial_number=f"{annual_sequence:05d}/{year % 100:02d}",
            **values, token_date=date.today(), sequence=sequence if doctor else annual_sequence,
            token_number=f"{doctor.token_prefix}-{sequence:03d}" if doctor else f"{annual_sequence:05d}/{year % 100:02d}"
        )
        self.db.add(token)
        self._audit(
            token,
            "token.created",
            actor,
            None,
            "waiting",
            detail={"source": token.source, "waiting_room": token.waiting_room},
        )
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            if payload.appointment_id:
                existing = self.db.scalar(select(QueueToken).where(QueueToken.appointment_id == payload.appointment_id))
                if existing:
                    return self._read(existing)
            raise HTTPException(409, "A token with this source already exists")
        return self._read(token)

    def list_tokens(self, doctor_id: str | None = None, waiting_room: str | None = None, shared_waiting: bool = False) -> list[TokenRead]:
        stmt = select(QueueToken).where(QueueToken.token_date == date.today())
        if doctor_id:
            stmt = stmt.where(or_(QueueToken.doctor_id == doctor_id, QueueToken.status == "waiting") if shared_waiting else QueueToken.doctor_id == doctor_id)
        if waiting_room:
            stmt = stmt.where(or_(QueueToken.waiting_room == waiting_room, QueueToken.waiting_room == ""))
        priority_weight = self._priority_weights()
        stmt = stmt.order_by(
            case((QueueToken.priority == "vip", 0), else_=1),
            case((QueueToken.status.in_(["called", "recalled", "in_progress"]), 0), (QueueToken.status == "waiting", 1), else_=2),
            case(priority_weight, value=QueueToken.priority, else_=100),
            QueueToken.sequence,
        )
        return [self._read(token) for token in self.db.scalars(stmt)]

    def call_next(self, doctor_id: str, actor: str | None = None) -> TokenRead:
        doctor = self.db.scalar(select(Doctor).where(Doctor.id == doctor_id).with_for_update())
        if not doctor or not doctor.is_active:
            raise HTTPException(404, "Doctor not found or inactive")
        control = self.db.get(QueueControl, doctor_id)
        if control and control.is_paused:
            raise HTTPException(409, f"Queue is paused: {control.reason or 'No reason provided'}")
        token = self.db.scalar(
            select(QueueToken)
            .where(
                QueueToken.token_date == date.today(),
                QueueToken.status == "waiting",
                QueueToken.priority != "vip",
            )
            .order_by(
                case(self._priority_weights(), value=QueueToken.priority, else_=100),
                QueueToken.scheduled_at,
                QueueToken.created_at,
            )
            .limit(1)
            .with_for_update()
        )
        if not token:
            raise HTTPException(404, "No waiting patient found")
        return self.call(token.id, doctor_id, action_name="doctor.call_next", actor=actor)

    def call(
        self, token_id: str, doctor_id: str, *, action_name: str = "doctor.manual_call", actor: str | None = None
    ) -> TokenRead:
        doctor = self.db.scalar(select(Doctor).where(Doctor.id == doctor_id).with_for_update())
        if not doctor or not doctor.is_active:
            raise HTTPException(404, "Doctor not found or inactive")
        token = self.db.scalar(select(QueueToken).where(QueueToken.id == token_id).with_for_update().execution_options(populate_existing=True))
        if not token or token.token_date != date.today():
            raise HTTPException(404, "Patient not found")
        if token.priority == "vip":
            raise HTTPException(409, "VIP patients must be called physically; electronic calling is disabled")
        if token.status == "called" and token.doctor_id == doctor_id:
            return self._read(token)
        if token.status != "waiting":
            raise HTTPException(409, "Only waiting patients can be called; this patient is already being handled")
        self._assign_for_call(token, doctor)
        previous_status = token.status
        token.status = "called"
        token.called_at = datetime.utcnow()
        event = CallEvent(
            token_id=token.id,
            action="call",
            waiting_room=token.waiting_room,
            payload={
                "token_number": token.token_number,
                "patient_name": token.patient_name,
                "doctor_name": token.doctor_name,
                "room_number": token.room_number,
            },
        )
        self.db.add(event)
        self.db.flush()
        self._audit(
            token,
            action_name,
            actor or doctor_id,
            previous_status,
            "called",
            detail={"waiting_room": token.waiting_room, "event_id": event.id},
        )
        self.db.commit()
        return self._read(token)

    def _assign_for_call(self, token: QueueToken, doctor: Doctor) -> None:
        occupied = self.db.scalar(select(QueueToken.id).where(
            QueueToken.doctor_id == doctor.id, QueueToken.token_date == date.today(),
            QueueToken.status.in_(["called", "recalled", "in_progress"]), QueueToken.id != token.id
        ).limit(1))
        if occupied:
            raise HTTPException(409, "Finish, skip or cancel the current patient before calling another")
        room = self.db.get(WaitingRoom, doctor.waiting_room_id)
        if not room or not room.is_active:
            raise HTTPException(409, "Radiographer has no active waiting room")
        same_radiographer = token.doctor_id == doctor.id
        if not same_radiographer:
            token.sequence = self.db.scalar(select(func.coalesce(func.max(QueueToken.sequence), 0)).where(
                QueueToken.doctor_id == doctor.id, QueueToken.token_date == date.today())) + 1
        token.doctor_id = doctor.id
        token.doctor_name = doctor.name
        token.department = doctor.department
        token.room_number = token.room_number if same_radiographer and token.room_number else doctor.room_number
        token.waiting_room = room.code

    def action(self, token_id: str, doctor_id: str, action: str, reason: str | None, actor: str) -> TokenRead:
        doctor = self.db.scalar(select(Doctor).where(Doctor.id == doctor_id).with_for_update())
        if not doctor or not doctor.is_active:
            raise HTTPException(404, "Radiographer not found")
        token = self.db.scalar(select(QueueToken).where(QueueToken.id == token_id).with_for_update().execution_options(populate_existing=True))
        if not token or token.token_date != date.today():
            raise HTTPException(404, "Patient not found")
        if token.doctor_id != doctor_id and not (token.status == "waiting" and action in {"call_physically", "cancel"}):
            raise HTTPException(409, "This patient is already being handled by another radiographer")
        transitions = {
            "start": ({"waiting", "called", "recalled"}, "in_progress"),
            "call_physically": ({"waiting"}, "in_progress"),
            "complete": ({"in_progress"}, "completed"),
            "skip": ({"called", "recalled"}, "skipped"),
            "recall": ({"skipped", "called", "recalled"}, "recalled"),
            "no_show": ({"called", "recalled", "skipped"}, "no_show"),
            "cancel": ({"waiting", "called", "recalled", "skipped", "in_progress"}, "cancelled"),
        }
        allowed, new_status = transitions[action]
        if token.status not in allowed:
            raise HTTPException(409, f"Cannot {action.replace('_', ' ')} a token in {token.status} state")
        if action == "start" and token.status == "waiting" and token.priority != "vip":
            raise HTTPException(409, "Only a physically called VIP patient can start directly from the waiting list")
        if action in {"skip", "no_show", "cancel"} and not reason:
            raise HTTPException(422, "A reason is required for this action")
        if action == "call_physically" and token.priority != "vip":
            raise HTTPException(409, "Physical calling is reserved for VIP patients")
        previous_status = token.status
        if action == "recall":
            if token.priority == "vip":
                raise HTTPException(409, "VIP patients must be called physically; electronic recall is disabled")
            queue_setting = self.db.get(AppSetting, "queue")
            recall_limit = int((queue_setting.value if queue_setting else {}).get("recall_limit", 3))
            if token.recall_count >= recall_limit:
                raise HTTPException(409, f"Recall limit of {recall_limit} has been reached")
        if action == "call_physically":
            self._assign_for_call(token, doctor)
        token.status = new_status
        now = datetime.utcnow()
        timestamp_fields = {
            "start": "started_at",
            "call_physically": "started_at",
            "complete": "completed_at",
            "skip": "skipped_at",
            "recall": "recalled_at",
            "no_show": "no_show_at",
            "cancel": "cancelled_at",
        }
        setattr(token, timestamp_fields[action], now)
        if action == "call_physically":
            token.called_at = now
        if action == "recall":
            token.recall_count += 1
            token.called_at = now
            event = CallEvent(
                token_id=token.id,
                action="recall",
                waiting_room=token.waiting_room,
                payload={
                    "token_number": token.token_number,
                    "patient_name": token.patient_name,
                    "doctor_name": token.doctor_name,
                    "room_number": token.room_number,
                },
            )
            self.db.add(event)
            self.db.flush()
            event_id = event.id
        else:
            event_id = None
        detail = {"doctor_id": doctor_id, "waiting_room": token.waiting_room}
        if event_id:
            detail["event_id"] = event_id
        self._audit(token, f"queue.{action}", actor, previous_status, new_status, reason=reason, detail=detail)
        self.db.commit()
        return self._read(token)

    def set_paused(self, doctor_id: str, is_paused: bool, reason: str, actor: str) -> QueueControl:
        doctor = self.db.scalar(select(Doctor).where(Doctor.id == doctor_id).with_for_update())
        if not doctor:
            raise HTTPException(404, "Doctor not found")
        control = self.db.get(QueueControl, doctor_id)
        if not control:
            control = QueueControl(doctor_id=doctor_id)
            self.db.add(control)
        control.is_paused = is_paused
        control.reason = reason
        control.updated_by = actor
        self.db.add(
            AuditEvent(
                action="queue.paused" if is_paused else "queue.resumed",
                actor=actor,
                reason=reason,
                detail={"doctor_id": doctor_id},
            )
        )
        self.db.commit()
        self.db.refresh(control)
        return control

    def transfer(self, token_id: str, doctor_id: str, reason: str, actor: str, expected_doctor_id: str | None = None) -> TokenRead:
        doctor = self.db.scalar(select(Doctor).where(Doctor.id == doctor_id).with_for_update())
        token = self.db.scalar(select(QueueToken).where(QueueToken.id == token_id).with_for_update().execution_options(populate_existing=True))
        if expected_doctor_id is not None and token and token.doctor_id != expected_doctor_id:
            raise HTTPException(409, "This patient has already moved to another queue")
        if not token or token.token_date != date.today():
            raise HTTPException(404, "Queue token not found")
        if token.status not in {"waiting", "skipped"}:
            raise HTTPException(409, "Only waiting or skipped tokens can be transferred")
        if not doctor or not doctor.is_active:
            raise HTTPException(404, "Destination doctor not found")
        room = self.db.get(WaitingRoom, doctor.waiting_room_id)
        if not room or not room.is_active:
            raise HTTPException(409, "Destination has no active waiting room")
        if token.priority == "vip":
            raise HTTPException(409, "VIP rooms are assigned automatically")
        previous_status = token.status
        previous_doctor = token.doctor_id
        sequence = (
            self.db.scalar(
                select(func.coalesce(func.max(QueueToken.sequence), 0)).where(
                    QueueToken.token_date == date.today(), QueueToken.doctor_id == doctor.id
                )
            )
            + 1
        )
        token.doctor_id, token.doctor_name = doctor.id, doctor.name
        token.department, token.room_number = doctor.department, doctor.room_number
        token.waiting_room, token.sequence = room.code, sequence
        token.token_number = f"{doctor.token_prefix}-{sequence:03d}"
        token.status = "waiting"
        self._audit(
            token,
            "queue.transferred",
            actor,
            previous_status,
            "waiting",
            reason=reason,
            detail={"from_doctor_id": previous_doctor, "to_doctor_id": doctor.id},
        )
        self.db.commit()
        return self._read(token)

    def available_patients(self, doctor_id: str) -> list[TokenRead]:
        doctor = self.db.scalar(select(Doctor).where(Doctor.id == doctor_id).with_for_update())
        if not doctor or not doctor.is_active:
            raise HTTPException(404, "Radiographer not found")
        occupied = self.db.scalar(select(QueueToken.id).where(
            QueueToken.doctor_id == doctor_id, QueueToken.token_date == date.today(),
            QueueToken.status.in_(["waiting", "called", "recalled", "in_progress"])
        ).limit(1))
        if occupied:
            raise HTTPException(409, "Your queue must be empty before taking a patient from another room")
        return [self._read(token) for token in self.db.scalars(select(QueueToken).where(
            QueueToken.token_date == date.today(), or_(QueueToken.doctor_id != doctor_id, QueueToken.doctor_id.is_(None)),
            QueueToken.status == "waiting", QueueToken.priority != "vip"
        ).order_by(QueueToken.created_at))]

    def claim_patient(self, token_id: str, doctor_id: str, actor: str) -> TokenRead:
        available = self.available_patients(doctor_id)
        candidate = next((token for token in available if token.id == token_id), None)
        if not candidate:
            raise HTTPException(409, "This patient is no longer available for reassignment")
        return self.transfer(token_id, doctor_id, "Taken by an idle radiographer", actor, expected_doctor_id=candidate.doctor_id)

    def update_priority(self, token_id: str, priority: str, reason: str, actor: str) -> TokenRead:
        self._require_lookup("priority_category", priority)
        token = self.db.scalar(select(QueueToken).where(QueueToken.id == token_id).with_for_update())
        if not token or token.token_date != date.today():
            raise HTTPException(404, "Queue token not found")
        previous = token.priority
        token.priority = priority
        self._audit(
            token,
            "queue.priority_changed",
            actor,
            token.status,
            token.status,
            reason=reason,
            detail={"previous_priority": previous, "new_priority": priority},
        )
        self.db.commit()
        return self._read(token)

    def update_room(self, token_id: str, room_number: str, actor: str) -> TokenRead:
        token = self.db.scalar(select(QueueToken).where(QueueToken.id == token_id).with_for_update())
        if not token or token.token_date != date.today():
            raise HTTPException(404, "Queue token not found")
        if token.priority == "vip":
            raise HTTPException(409, "VIP rooms are assigned automatically")
        if token.status != "waiting":
            raise HTTPException(409, "Room number cannot be changed after the patient has been called")
        room_number = room_number.strip()
        if not room_number:
            raise HTTPException(422, "Room number cannot be empty")
        self._require_lookup("room_number", room_number)
        previous_room = token.room_number
        token.room_number = room_number
        self._audit(
            token,
            "queue.room_changed",
            actor,
            token.status,
            token.status,
            detail={"previous_room_number": previous_room, "new_room_number": token.room_number},
        )
        self.db.commit()
        return self._read(token)

    def _require_lookup(self, category: str, value: str) -> LookupOption:
        item = self.db.scalar(
            select(LookupOption).where(
                LookupOption.category == category, LookupOption.value == value, LookupOption.is_active.is_(True)
            )
        )
        if not item:
            if not self.db.scalar(select(LookupOption.id).where(LookupOption.category == category).limit(1)):
                return LookupOption(category=category, value=value, label=value)
            raise HTTPException(422, f"Invalid or inactive {category.replace('_', ' ')}")
        return item

    def _priority_weights(self) -> dict[str, int]:
        configured = list(
            self.db.scalars(
                select(LookupOption).where(
                    LookupOption.category == "priority_category", LookupOption.is_active.is_(True)
                )
            )
        )
        if not configured:
            return PRIORITY_WEIGHT
        return {item.value: int(item.metadata_json.get("weight", item.sort_order)) for item in configured}

    def display(self, waiting_room: str) -> DisplayRead:
        clinical_fields = dict.fromkeys(("age", "unit", "mri_area", "contrast", "film", "report", "patient_source", "beneficiary_type", "service_status", "entitlement", "sponsor_rank", "family_relationship", "summary_category"))
        room_tokens = [token.model_copy(update=clinical_fields) for token in self.list_tokens(waiting_room=waiting_room)]
        all_tokens = [token.model_copy(update=clinical_fields) for token in self.list_tokens()]
        active_calls = sorted(
            (token for token in all_tokens if token.status in {"called", "recalled"} and token.priority != "vip"),
            key=lambda token: token.called_at or token.created_at,
            reverse=True,
        )
        current = active_calls[0] if active_calls else None
        display_setting = self.db.get(AppSetting, "display")
        values = display_setting.value if display_setting else {}
        next_count = max(1, min(int(values.get("next_token_count", 5)), 10))
        upcoming = [token for token in room_tokens if token.status == "waiting" and token.priority != "vip"][:next_count]
        privacy_mode = values.get("privacy_mode", "initials")
        # A called patient's full name is required for an unambiguous visual and
        # audio announcement. Privacy masking remains enabled for upcoming names.
        upcoming = [self._public_token(token, privacy_mode) for token in upcoming]
        current = active_calls[0] if active_calls else None
        announcement = None
        if current:
            doctor_name = current.doctor_name.strip()
            lowered_name = doctor_name.lower()
            for prefix in ("doctor ", "dr. ", "dr "):
                if lowered_name.startswith(prefix):
                    doctor_name = doctor_name[len(prefix) :].strip()
                    break
            identity = f"{current.service_number}, {current.patient_name}" if current.service_number else current.patient_name
            announcement = (
                f"{identity}. Please proceed to "
                f"Doctor {doctor_name}, room {current.room_number}."
            )
        return DisplayRead(
            waiting_room=waiting_room,
            current=current,
            active_calls=active_calls,
            next_tokens=upcoming,
            announcement=announcement,
        )

    def _audit(
        self,
        token: QueueToken,
        action: str,
        actor: str,
        previous_status: str | None,
        new_status: str | None,
        *,
        reason: str | None = None,
        detail: dict | None = None,
    ) -> None:
        self.db.add(
            AuditEvent(
                action=action,
                actor=actor,
                token_id=token.id,
                previous_status=previous_status,
                new_status=new_status,
                reason=reason,
                detail=detail or {},
            )
        )

    @staticmethod
    def _public_token(token: TokenRead, mode: str) -> TokenRead:
        if mode == "full":
            return token
        if mode == "token_only":
            return token.model_copy(update={"patient_name": "Patient"})
        parts = token.patient_name.split()
        masked = " ".join([parts[0], *[f"{part[0]}." for part in parts[1:] if part]]) if parts else "Patient"
        return token.model_copy(update={"patient_name": masked})

    def _get(self, token_id: str, doctor_id: str) -> QueueToken:
        token = self.db.scalar(select(QueueToken).where(QueueToken.id == token_id).with_for_update())
        if not token or token.token_date != date.today() or token.doctor_id != doctor_id:
            raise HTTPException(404, "Queue token not found")
        return token

    @staticmethod
    def _read(token: QueueToken) -> TokenRead:
        now = datetime.utcnow()
        wait_end = token.called_at or token.started_at or token.completed_at or token.cancelled_at or now
        waiting_minutes = max(int((wait_end - token.created_at).total_seconds() // 60), 0)
        return TokenRead.model_validate(token).model_copy(update={"waiting_minutes": waiting_minutes})
