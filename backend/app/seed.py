from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, inspect, select

from .auth import hash_password
from .database import SessionLocal
from .models import (
    AppSetting,
    Doctor,
    LookupOption,
    QueueToken,
    ScheduleSlot,
    User,
    WaitingRoom,
)

ROOMS = [
    ("waiting-room-1", "WR-1", "Medicine Waiting Room", "2nd Floor", "Medicine & General"),
    ("waiting-room-2", "WR-2", "Cardiology Waiting Room", "3rd Floor", "Cardiology"),
    ("waiting-room-3", "WR-3", "Paediatrics Waiting Room", "1st Floor", "Paediatrics"),
    ("waiting-room-4", "WR-4", "Orthopaedics Waiting Room", "4th Floor", "Orthopaedics"),
]
DOCTORS = [
    ("dr-khan", "Dr. Ayesha Khan", "Medicine", "Consultant", "205", "waiting-room-1", "AK"),
    ("dr-rahman", "Dr. Farhan Rahman", "Cardiology", "Senior Consultant", "312", "waiting-room-2", "FR"),
    ("dr-sultana", "Dr. Nusrat Sultana", "Paediatrics", "Consultant", "118", "waiting-room-3", "NS"),
    ("dr-chowdhury", "Dr. Imran Chowdhury", "Orthopaedics", "Senior Consultant", "407", "waiting-room-4", "IC"),
]
PATIENTS = [
    ("Md. Rahim Uddin", "01711000001", "appointment", "normal", "army", "Major", "BA-10234"),
    ("Nusrat Jahan", "01812000002", "walk_in", "priority", "dependant", None, None),
    ("Abdul Karim", "01913000003", "walk_in", "normal", "retired", "Sergeant", "RET-4217"),
    ("Farzana Akter", "01614000004", "appointment", "normal", "civilian", None, None),
]
LOOKUPS = {
    "patient_source": [("opd", "OPD"), ("ipd", "IPD / Ward"), ("emergency", "Emergency"), ("referral", "Referral"), ("walk_in", "Walk-in"), ("appointment", "Appointment")],
    "department": [
        ("medicine", "Medicine"),
        ("cardiology", "Cardiology"),
        ("paediatrics", "Paediatrics"),
        ("orthopaedics", "Orthopaedics"),
    ],
    "designation": [
        ("mr", "Mr."),
        ("mrs", "Mrs."),
        ("ms", "Ms."),
        ("miss", "Miss"),
        ("master", "Master"),
        ("dr", "Dr."),
    ],
    "room_number": [(doctor[4], f"Room {doctor[4]}") for doctor in DOCTORS],
    "sex": [("male", "Male"), ("female", "Female"), ("other", "Other")],
    "service_category": [
        ("army", "Bangladesh Army"),
        ("navy", "Bangladesh Navy"),
        ("air_force", "Bangladesh Air Force"),
        ("retired", "Retired service"),
        ("dependant", "Service dependant"),
        ("civilian", "Civilian"),
    ],
    "rank_relationship": [
        ("brigadier_general", "Brigadier General"),
        ("colonel", "Colonel"),
        ("lieutenant_colonel", "Lieutenant Colonel"),
        ("major", "Major"),
        ("captain", "Captain"),
        ("lieutenant", "Lieutenant"),
        ("warrant_officer", "Warrant Officer"),
        ("sergeant", "Sergeant"),
        ("corporal", "Corporal"),
        ("shoinik", "Shoinik / Sainik"),
        ("vip", "VIP"),
        ("officer", "Officer"),
        ("jco", "JCO"),
        ("soldier", "Soldier"),
        ("spouse", "Spouse"),
        ("child", "Child"),
        ("parent", "Parent"),
        ("other", "Other"),
    ],
    "priority_category": [
        ("emergency", "Emergency"),
        ("urgent", "Urgent"),
        ("pregnant", "Pregnant"),
        ("disabled", "Disabled"),
        ("elderly", "Elderly"),
        ("vip", "VIP"),
        ("follow_up", "Follow-up"),
        ("normal", "Normal"),
    ],
    "appointment_reason": [
        ("new_consultation", "New consultation"),
        ("follow_up", "Follow-up"),
        ("review", "Review"),
        ("medical_board", "Medical board"),
        ("other", "Other"),
    ],
}


def seed() -> None:
    now, today = datetime.utcnow(), date.today()
    with SessionLocal() as db:
        def ensure(item):
            identity = tuple(getattr(item, column.key) for column in inspect(type(item)).primary_key)
            if db.get(type(item), identity) is None:
                db.add(item)

        for room_id, code, name, floor, label in ROOMS:
            ensure(
                WaitingRoom(
                    id=room_id,
                    code=code,
                    name=name,
                    floor=floor,
                    display_label=label,
                    audio_enabled=True,
                    display_enabled=True,
                    is_active=True,
                )
            )
        db.flush()
        for doctor_id, name, department, designation, room, waiting_room_id, prefix in DOCTORS:
            ensure(
                Doctor(
                    id=doctor_id,
                    name=name,
                    department=department,
                    designation=designation,
                    room_number=room,
                    waiting_room_id=waiting_room_id,
                    token_prefix=prefix,
                    is_active=True,
                )
            )
        db.flush()
        admin_username = os.getenv("CMH_SMS_ADMIN_USERNAME", "admin").lower()
        admin_password = os.getenv("CMH_SMS_ADMIN_PASSWORD")
        admin = db.scalar(select(User).where(User.username == admin_username))
        if not admin and admin_password:
            db.add(
                User(
                    username=admin_username,
                    full_name=os.getenv("CMH_SMS_ADMIN_NAME", "CMH System Administrator"),
                    password_hash=hash_password(admin_password),
                    role="admin",
                    is_active=True,
                )
            )
        ensure(
            AppSetting(
                key="display",
                value={
                    "privacy_mode": "initials",
                    "next_token_count": 5,
                    "ticker_message": "Please keep your registration slip ready",
                },
                description="Public display privacy and content",
            )
        )
        ensure(
            AppSetting(
                key="queue",
                value={"ordering_policy": "priority_then_sequence", "recall_limit": 3, "late_grace_minutes": 15},
                description="Queue ordering and transition policy",
            )
        )
        ensure(
            AppSetting(
                key="announcement",
                value={"language_order": ["bn", "en"], "repeat_count": 1, "rate": 0.88, "volume": 1.0, "voice_mode": "auto", "cache_max_files": 40},
                description="Bilingual audio announcement policy",
            )
        )
        for category, options in LOOKUPS.items():
            for sort_order, (value, label) in enumerate(options):
                item = db.scalar(
                    select(LookupOption).where(LookupOption.category == category, LookupOption.value == value)
                )
                metadata = {"weight": sort_order} if category == "priority_category" else {}
                if category == "rank_relationship" and value in {"brigadier_general", "vip"}:
                    metadata = {"priority": "vip"}
                if not item:
                    db.add(
                        LookupOption(
                            category=category,
                            value=value,
                            label=label,
                            sort_order=sort_order,
                            metadata_json=metadata,
                            is_active=True,
                        )
                    )
        from .monthly_report import CLASSIFICATION_LOOKUPS, RANK_GROUPS
        for category, options in CLASSIFICATION_LOOKUPS.items():
            for order, (value, label) in enumerate(options):
                if not db.scalar(select(LookupOption).where(LookupOption.category == category, LookupOption.value == value)):
                    db.add(LookupOption(category=category, value=value, label=label, sort_order=order, metadata_json={"report_code": value}, is_active=True))
        # Initialize mappings once; future administrator edits (including blank mappings) persist.
        if not db.get(AppSetting, "mri_rank_mapping_initialized"):
            for item in db.scalars(select(LookupOption).where(LookupOption.category == "rank_relationship")):
                if "report_group" not in (item.metadata_json or {}) and item.value in RANK_GROUPS:
                    item.metadata_json = {**(item.metadata_json or {}), "report_group": RANK_GROUPS[item.value]}
            db.add(AppSetting(key="mri_rank_mapping_initialized", value={"version": 1}, description="Initial MRI rank mapping applied"))
        db.flush()
        # Keep two weeks of baseline slots available without overwriting any
        # administrator-created schedule. Fridays are excluded.
        for day_offset in range(14):
            slot_day = today + timedelta(days=day_offset)
            if slot_day.weekday() == 4:
                continue
            for doctor_index, doctor in enumerate(DOCTORS):
                starts_at = datetime.combine(slot_day, datetime.min.time()).replace(hour=9 + doctor_index)
                if not db.scalar(
                    select(ScheduleSlot).where(ScheduleSlot.doctor_id == doctor[0], ScheduleSlot.starts_at == starts_at)
                ):
                    db.add(
                        ScheduleSlot(
                            doctor_id=doctor[0],
                            starts_at=starts_at,
                            ends_at=starts_at + timedelta(hours=2),
                            capacity=20,
                            is_active=True,
                        )
                    )
        if os.getenv("CMH_SMS_SEED_DEMO", "false").lower() in {"1", "true", "yes"}:
            db.execute(delete(QueueToken).where(QueueToken.token_date == today, QueueToken.id.like("demo-%")))
            for doctor_index, doctor in enumerate(DOCTORS):
                doctor_id, doctor_name, department, _, room_number, waiting_room_id, prefix = doctor
                real_token_count = (
                    db.scalar(
                        select(func.count(QueueToken.id)).where(
                            QueueToken.token_date == today,
                            QueueToken.doctor_id == doctor_id,
                            ~QueueToken.id.like("demo-%"),
                        )
                    )
                    or 0
                )
                if real_token_count:
                    continue
                for patient_index, (
                    patient_name,
                    phone,
                    source,
                    priority,
                    service_category,
                    rank,
                    service_number,
                ) in enumerate(PATIENTS):
                    sequence = patient_index + 1
                    is_called = patient_index == 0
                    db.add(
                        QueueToken(
                            id=f"demo-{today.isoformat()}-{doctor_index + 1}-{sequence}",
                            token_date=today,
                            sequence=sequence,
                            token_number=f"{prefix}-{sequence:03d}",
                            patient_name=patient_name,
                            patient_phone=phone,
                            doctor_id=doctor_id,
                            doctor_name=doctor_name,
                            department=department,
                            room_number=room_number,
                            waiting_room="WR-1" if is_called else ROOMS[(doctor_index + patient_index) % len(ROOMS)][1],
                            source=source,
                            priority=priority,
                            service_category=service_category,
                            rank=rank,
                            service_number=service_number,
                            status="called" if is_called else "waiting",
                            created_at=now - timedelta(minutes=(4 - patient_index) * 7 + doctor_index),
                            called_at=now - timedelta(minutes=2) if is_called else None,
                        )
                    )
        db.commit()
    print(f"Seed complete: {len(ROOMS)} rooms and {len(DOCTORS)} doctors.")


if __name__ == "__main__":
    seed()
