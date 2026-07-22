from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TokenCreate(BaseModel):
    patient_name: str = Field(min_length=2, max_length=160)
    patient_phone: str = Field(min_length=6, max_length=30)
    service_category: Literal["army", "navy", "air_force", "retired", "dependant", "civilian"] = "civilian"
    rank: str | None = Field(default=None, max_length=60)
    service_number: str | None = Field(default=None, max_length=40)
    doctor_id: str
    doctor_name: str
    department: str
    room_number: str
    waiting_room: Literal["WR-1", "WR-2", "WR-3", "WR-4"] = "WR-1"
    source: Literal["walk_in", "appointment"] = "walk_in"
    priority: Literal["normal", "priority"] = "normal"


class TokenRead(TokenCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    token_number: str
    sequence: int
    status: str
    created_at: datetime
    called_at: datetime | None = None
    completed_at: datetime | None = None
    started_at: datetime | None = None
    skipped_at: datetime | None = None
    recalled_at: datetime | None = None
    no_show_at: datetime | None = None
    cancelled_at: datetime | None = None
    recall_count: int = 0
    waiting_minutes: int = 0


class DisplayRead(BaseModel):
    waiting_room: str
    current: TokenRead | None
    active_calls: list[TokenRead]
    next_tokens: list[TokenRead]
    announcement: str | None


class DashboardRead(BaseModel):
    waiting: int
    called: int
    completed: int
    average_wait_minutes: int


class QueueActionRequest(BaseModel):
    action: Literal["start", "complete", "skip", "recall", "no_show", "cancel"]
    reason: str | None = Field(default=None, max_length=240)
    actor: str = Field(default="staff.operator", min_length=2, max_length=120)


class PriorityUpdateRequest(BaseModel):
    priority: Literal["normal", "priority"]
    reason: str = Field(min_length=2, max_length=240)
    actor: str = Field(default="reception.operator", min_length=2, max_length=120)


class SettingUpdate(BaseModel):
    value: dict


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    action: str
    actor: str
    token_id: str | None
    previous_status: str | None
    new_status: str | None
    reason: str | None
    detail: dict
    created_at: datetime
