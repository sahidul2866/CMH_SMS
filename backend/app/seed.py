from __future__ import annotations

from datetime import date, datetime, timedelta
from sqlalchemy import delete, func, select
from .database import SessionLocal
from .models import AppSetting, Doctor, QueueToken, WaitingRoom

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

def seed() -> None:
    now, today = datetime.utcnow(), date.today()
    with SessionLocal() as db:
        for room_id, code, name, floor, label in ROOMS:
            db.merge(WaitingRoom(id=room_id, code=code, name=name, floor=floor, display_label=label, audio_enabled=True, display_enabled=True, is_active=True))
        for doctor_id, name, department, designation, room, waiting_room_id, prefix in DOCTORS:
            db.merge(Doctor(id=doctor_id, name=name, department=department, designation=designation, room_number=room, waiting_room_id=waiting_room_id, token_prefix=prefix, is_active=True))
        db.merge(AppSetting(key="display", value={"privacy_mode": "initials", "next_token_count": 5, "ticker_message": "Please keep your token ready"}, description="Public display privacy and content"))
        db.merge(AppSetting(key="queue", value={"ordering_policy": "priority_then_sequence", "recall_limit": 3, "late_grace_minutes": 15}, description="Queue ordering and transition policy"))
        db.merge(AppSetting(key="announcement", value={"language_order": ["bn", "en"], "repeat_count": 1, "rate": 0.88, "volume": 1.0}, description="Bilingual audio announcement policy"))
        db.flush()
        db.execute(delete(QueueToken).where(QueueToken.token_date == today, QueueToken.id.like("demo-%")))
        for doctor_index, doctor in enumerate(DOCTORS):
            doctor_id, doctor_name, department, _, room_number, waiting_room_id, prefix = doctor
            real_token_count = db.scalar(select(func.count(QueueToken.id)).where(
                QueueToken.token_date == today, QueueToken.doctor_id == doctor_id,
                ~QueueToken.id.like("demo-%"))) or 0
            if real_token_count:
                continue
            for patient_index, (patient_name, phone, source, priority, service_category, rank, service_number) in enumerate(PATIENTS):
                sequence = patient_index + 1
                is_called = patient_index == 0
                db.add(QueueToken(id=f"demo-{doctor_index + 1}-{sequence}", token_date=today, sequence=sequence,
                    token_number=f"{prefix}-{sequence:03d}", patient_name=patient_name, patient_phone=phone,
                    doctor_id=doctor_id, doctor_name=doctor_name, department=department, room_number=room_number,
                    waiting_room="WR-1" if is_called else ROOMS[(doctor_index + patient_index) % len(ROOMS)][1], source=source, priority=priority,
                    service_category=service_category, rank=rank, service_number=service_number,
                    status="called" if is_called else "waiting",
                    created_at=now - timedelta(minutes=(4 - patient_index) * 7 + doctor_index),
                    called_at=now - timedelta(minutes=2) if is_called else None))
        db.commit()
    print(f"Seed complete: {len(ROOMS)} rooms, {len(DOCTORS)} doctors, {len(DOCTORS) * len(PATIENTS)} queue tokens.")

if __name__ == "__main__":
    seed()
