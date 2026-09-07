from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class WaitingRoom(Base):
    __tablename__ = "waiting_rooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    floor: Mapped[str] = mapped_column(String(40), nullable=False)
    display_label: Mapped[str] = mapped_column(String(120), nullable=False)
    audio_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    designation: Mapped[str] = mapped_column(String(120), nullable=False)
    room_number: Mapped[str] = mapped_column(String(30), nullable=False)
    waiting_room_id: Mapped[str] = mapped_column(String(36), ForeignKey("waiting_rooms.id"), nullable=False, index=True)
    token_prefix: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    patient_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(30), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    mobile: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class ScheduleSlot(Base):
    __tablename__ = "schedule_slots"
    __table_args__ = (UniqueConstraint("doctor_id", "starts_at", name="uq_doctor_slot_start"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    doctor_id: Mapped[str] = mapped_column(String(60), ForeignKey("doctors.id"), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    appointment_number: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    patient_id: Mapped[str] = mapped_column(String(36), ForeignKey("patients.id"), nullable=False, index=True)
    doctor_id: Mapped[str] = mapped_column(String(60), ForeignKey("doctors.id"), nullable=False, index=True)
    slot_id: Mapped[str] = mapped_column(String(36), ForeignKey("schedule_slots.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled", index=True)
    reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RegistrationCounter(Base):
    __tablename__ = "registration_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class QueueToken(Base):
    __tablename__ = "queue_tokens"
    __table_args__ = (UniqueConstraint("token_date", "doctor_id", "sequence", name="uq_daily_doctor_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    token_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    token_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(30), nullable=True, unique=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(160), nullable=True)
    mri_area: Mapped[str | None] = mapped_column(String(240), nullable=True)
    contrast: Mapped[int | None] = mapped_column(Integer, nullable=True)
    film: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    beneficiary_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    service_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entitlement: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sponsor_rank: Mapped[str | None] = mapped_column(String(100), nullable=True)
    family_relationship: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    patient_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    patient_title: Mapped[str | None] = mapped_column(String(30), nullable=True)
    patient_name: Mapped[str] = mapped_column(String(160), nullable=False)
    patient_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    service_category: Mapped[str] = mapped_column(String(30), nullable=False, default="civilian")
    rank: Mapped[str | None] = mapped_column(String(60), nullable=True)
    service_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    doctor_id: Mapped[str | None] = mapped_column(String(60), ForeignKey("doctors.id"), nullable=True, index=True)
    doctor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    room_number: Mapped[str] = mapped_column(String(30), nullable=False)
    waiting_room: Mapped[str] = mapped_column(String(30), nullable=False, default="WR-1", index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="walk_in")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="waiting", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    called_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    skipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recalled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    no_show_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recall_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    patient_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("patients.id"), nullable=True, index=True)
    appointment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("appointments.id"), nullable=True, unique=True, index=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    token_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("queue_tokens.id"), nullable=True, index=True)
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    doctor_id: Mapped[str | None] = mapped_column(String(60), ForeignKey("doctors.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class RoleDefinition(Base):
    __tablename__ = "role_definitions"

    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    access_profile: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class QueueControl(Base):
    __tablename__ = "queue_controls"

    doctor_id: Mapped[str] = mapped_column(String(60), ForeignKey("doctors.id"), primary_key=True)
    is_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DeviceEndpoint(Base):
    __tablename__ = "device_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    waiting_room: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    client_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_acknowledged_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    fault: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class CallEvent(Base):
    __tablename__ = "call_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    token_id: Mapped[str] = mapped_column(String(36), ForeignKey("queue_tokens.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    waiting_room: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class LookupOption(Base):
    __tablename__ = "lookup_options"
    __table_args__ = (UniqueConstraint("category", "value", name="uq_lookup_category_value"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Holiday(Base):
    __tablename__ = "holidays"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SmsMessage(Base):
    __tablename__ = "sms_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    mobile: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    provider_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
