from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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


class QueueToken(Base):
    __tablename__ = "queue_tokens"
    __table_args__ = (UniqueConstraint("token_date", "doctor_id", "sequence", name="uq_daily_doctor_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    token_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    token_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    patient_name: Mapped[str] = mapped_column(String(160), nullable=False)
    patient_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    service_category: Mapped[str] = mapped_column(String(30), nullable=False, default="civilian")
    rank: Mapped[str | None] = mapped_column(String(60), nullable=True)
    service_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(60), ForeignKey("doctors.id"), nullable=False, index=True)
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
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
