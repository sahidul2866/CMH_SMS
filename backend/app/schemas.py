from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportClassification(BaseModel):
    beneficiary_type: str | None = Field(default=None, max_length=100)
    service_status: str | None = Field(default=None, max_length=100)
    entitlement: str | None = Field(default=None, max_length=100)
    sponsor_rank: str | None = Field(default=None, max_length=100)
    family_relationship: str | None = Field(default=None, max_length=100)


class TokenCreate(ReportClassification):
    age: int | None = Field(default=None, ge=0, le=150)
    unit: str | None = Field(default=None, max_length=160)
    mri_area: str | None = Field(default=None, max_length=240)
    contrast: int | None = Field(default=None, ge=0)
    film: int | None = Field(default=None, ge=0)
    report: str | None = Field(default=None, max_length=10000)
    patient_source: str | None = Field(default=None, max_length=100)

    patient_title: str | None = Field(default=None, max_length=30)
    patient_name: str = Field(min_length=2, max_length=160)
    patient_phone: str = Field(default="", max_length=30)
    service_category: str = Field(default="civilian", min_length=1, max_length=30)
    rank: str | None = Field(default=None, max_length=60)
    service_number: str | None = Field(default=None, max_length=40)
    doctor_id: str | None = None
    doctor_name: str = ""
    department: str = ""
    room_number: str = ""
    waiting_room: str = Field(default="", max_length=30)
    source: Literal["walk_in", "appointment"] = "walk_in"
    priority: str = Field(default="normal", min_length=1, max_length=20)
    patient_id: str | None = None
    appointment_id: str | None = None
    scheduled_at: datetime | None = None


class TokenRead(TokenCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    token_number: str
    serial_number: str | None = None
    summary_category: str | None = None
    token_date: date
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


class DashboardDoctorRead(BaseModel):
    doctor_id: str
    doctor_name: str
    department: str
    room_number: str
    waiting_room: str
    waiting: int
    called: int
    in_progress: int
    completed: int
    total: int
    average_wait_minutes: int
    vip: int


class DashboardRoomRead(BaseModel):
    room_number: str
    doctor_name: str = ""
    department: str = ""
    waiting_room: str = ""
    waiting: int = 0
    called: int = 0
    in_progress: int = 0
    completed: int = 0
    total: int = 0
    average_wait_minutes: int = 0
    vip: int = 0


class DashboardRead(BaseModel):
    scope: Literal["assigned", "all"]
    generated_at: datetime
    total: int
    waiting: int
    called: int
    in_progress: int
    completed: int
    average_wait_minutes: int
    vip_total: int
    vip_waiting: int
    vip_active: int
    vip_completed: int
    radiographers: list[DashboardDoctorRead]
    rooms: list[DashboardRoomRead] = []


class QueueActionRequest(BaseModel):
    action: Literal["start", "call_physically", "complete", "skip", "recall", "no_show", "cancel"]
    reason: str | None = Field(default=None, max_length=240)


class PriorityUpdateRequest(BaseModel):
    priority: str = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=2, max_length=240)


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


class LoginRequest(BaseModel):
    # Login accepts any non-empty credential shape and lets authentication
    # return one uniform 401 response. Password policy belongs on create/change,
    # not on the sign-in boundary where a validation error leaks policy details.
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9._-]+$", min_length=2, max_length=80)
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=10, max_length=200)
    role: str = Field(min_length=2, max_length=30, pattern=r"^[a-z][a-z0-9_-]+$")
    doctor_id: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    full_name: str
    role: str
    access_profile: str | None = None
    permissions: list[str] = Field(default_factory=list)
    doctor_id: str | None
    is_active: bool


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    password: str | None = Field(default=None, min_length=10, max_length=200)
    role: str | None = Field(default=None, min_length=2, max_length=30, pattern=r"^[a-z][a-z0-9_-]+$")
    doctor_id: str | None = None
    is_active: bool | None = None


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=30, pattern=r"^[a-z][a-z0-9_-]+$")
    display_name: str = Field(min_length=2, max_length=80)
    access_profile: Literal["admin", "reception", "radiographer", "auditor", "display"]
    description: str = Field(default="", max_length=240)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=80)
    access_profile: Literal["admin", "reception", "radiographer", "auditor", "display"] | None = None
    description: str | None = Field(default=None, max_length=240)
    permissions: list[str] | None = None


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    display_name: str
    access_profile: str
    description: str
    permissions: list[str]
    is_system: bool


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=10, max_length=200)


class PatientCreate(BaseModel):
    patient_number: str | None = Field(default=None, max_length=30)
    title: str | None = Field(default=None, max_length=30)
    name: str = Field(min_length=2, max_length=160)
    mobile: str = Field(min_length=1, max_length=30)
    date_of_birth: date | None = None
    sex: str | None = Field(default=None, max_length=20)


class PatientRead(PatientCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_number: str
    created_at: datetime


class SlotCreate(BaseModel):
    doctor_id: str
    starts_at: datetime
    ends_at: datetime
    capacity: int = Field(default=1, ge=1, le=100)


class SlotRead(SlotCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_active: bool


class AppointmentCreate(BaseModel):
    patient_id: str
    doctor_id: str
    slot_id: str
    reason: str | None = Field(default=None, max_length=240)
    notes: str | None = Field(default=None, max_length=1000)


class AppointmentUpdate(BaseModel):
    action: Literal["confirm", "reschedule", "cancel"]
    slot_id: str | None = None
    reason: str = Field(min_length=2, max_length=240)


class AppointmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    appointment_number: str
    patient_id: str
    doctor_id: str
    slot_id: str
    status: str
    reason: str | None
    notes: str | None
    created_by: str
    created_at: datetime
    checked_in_at: datetime | None


class QueueControlUpdate(BaseModel):
    is_paused: bool
    reason: str = Field(min_length=2, max_length=240)


class TransferRequest(BaseModel):
    doctor_id: str
    reason: str = Field(min_length=2, max_length=240)


class TokenRoomUpdateRequest(BaseModel):
    room_number: str = Field(min_length=1, max_length=30)


class DoctorCreate(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9._-]+$", min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=160)
    department: str = Field(min_length=2, max_length=120)
    designation: str = Field(min_length=2, max_length=120)
    room_number: str = Field(min_length=1, max_length=30)
    waiting_room_id: str
    token_prefix: str = Field(pattern=r"^[A-Z0-9]{1,8}$")


class DoctorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    department: str | None = Field(default=None, min_length=2, max_length=120)
    designation: str | None = Field(default=None, min_length=2, max_length=120)
    room_number: str | None = Field(default=None, min_length=1, max_length=30)
    waiting_room_id: str | None = None
    token_prefix: str | None = Field(default=None, min_length=1, max_length=8, pattern=r"^[A-Z0-9]{1,8}$")


class WaitingRoomCreate(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9._-]+$", min_length=2, max_length=36)
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=120)
    floor: str = Field(min_length=1, max_length=40)
    display_label: str = Field(min_length=2, max_length=120)
    audio_enabled: bool = True
    display_enabled: bool = True


class DeviceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    device_type: Literal["display", "audio"]
    waiting_room: str = Field(min_length=2, max_length=30)


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    device_type: str
    waiting_room: str
    is_active: bool
    last_heartbeat_at: datetime | None
    last_event_id: str | None
    last_acknowledged_event_id: str | None
    fault: str | None


class LookupCreate(BaseModel):
    category: str = Field(pattern=r"^[a-z][a-z0-9_]{1,49}$")
    value: str = Field(pattern=r"^[a-zA-Z0-9._-]+$", min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    sort_order: int = Field(default=0, ge=-10000, le=10000)
    metadata_json: dict = Field(default_factory=dict)
    is_active: bool = True


class LookupUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = Field(default=None, ge=-10000, le=10000)
    metadata_json: dict | None = None
    is_active: bool | None = None


class LookupRead(LookupCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str


class HolidayCreate(BaseModel):
    holiday_date: date
    name: str = Field(min_length=2, max_length=120)


class HolidayRead(HolidayCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_active: bool
