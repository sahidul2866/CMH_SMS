"""Stable account identities with room-based login names."""
import re

from fastapi import HTTPException
from sqlalchemy import select

from .models import Doctor, User


def room_username(db, doctor_id, account=None):
    room = db.scalar(select(Doctor).where(Doctor.id == doctor_id, Doctor.is_active.is_(True)).with_for_update())
    if not room:
        raise HTTPException(422, 'Assigned room does not exist or is inactive')
    base = re.sub(r'[^a-z0-9._-]+', '-', room.room_number.strip().lower()).strip('-')
    if not base:
        raise HTTPException(422, 'Room number must contain letters or digits for a user ID')
    conflict = select(User.id).where(User.username == base)
    if account:
        conflict = conflict.where(User.id != account.id)
    if db.scalar(conflict):
        raise HTTPException(409, f'User ID {base} already exists. Each room uses one login account.')
    return base
