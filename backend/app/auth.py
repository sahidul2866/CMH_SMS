from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, WebSocket, status
from sqlalchemy.orm import Session

from .database import get_db
from .models import RoleDefinition, User, UserSession

SESSION_COOKIE = "cmh_session"
SESSION_HOURS = int(os.getenv("CMH_SMS_SESSION_HOURS", "12"))
COOKIE_SECURE = os.getenv("CMH_SMS_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}
ROLES = {"admin", "reception", "radiographer", "auditor", "display"}
LEGACY_ROLE_PERMISSIONS = {
    "admin": {"*"},
    "reception": {
        "pages.reception", "pages.appointments", "pages.display", "directory.view", "master_data.view",
        "queue.serial.create", "queue.view", "queue.priority", "queue.transfer",
        "queue.print", "display.view", "patients.view", "patients.manage",
        "appointments.view", "appointments.manage", "appointments.check_in", "schedule.view",
    },
    "radiographer": {
        "pages.radiographer", "pages.dashboard", "dashboard.view", "directory.view", "master_data.view", "queue.view",
        "queue.call", "queue.action", "queue.pause", "audio.announce",
    },
    "radiography_head": {
        "pages.dashboard", "pages.radiographer", "pages.reports", "dashboard.view", "reports.view",
        "directory.view", "master_data.view", "queue.view",
    },
    "auditor": {"pages.dashboard", "pages.reports", "dashboard.view", "reports.view"},
    "display": {"pages.display", "directory.view", "display.view"},
}
DUMMY_PASSWORD_HASH = "pbkdf2_sha256$600000$00000000000000000000000000000000$e9cf86664f65f6113043257c35469267eafbc9d1b10b175e756e6b5929d836f5"


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual.hex(), expected)
    except (TypeError, ValueError):
        return False


def new_session(db: Session, user: User) -> str:
    raw = secrets.token_urlsafe(48)
    session_id = hashlib.sha256(raw.encode()).hexdigest()
    db.add(UserSession(id=session_id, user_id=user.id, expires_at=datetime.utcnow() + timedelta(hours=SESSION_HOURS)))
    db.commit()
    return raw


def revoke_session(db: Session, raw: str | None) -> None:
    if raw:
        session = db.get(UserSession, hashlib.sha256(raw.encode()).hexdigest())
        if session:
            db.delete(session)
            db.commit()


def user_for_session(db: Session, raw: str | None) -> User | None:
    if not raw:
        return None
    session = db.get(UserSession, hashlib.sha256(raw.encode()).hexdigest())
    if not session or session.expires_at <= datetime.utcnow():
        if session:
            db.delete(session)
            db.commit()
        return None
    user = db.get(User, session.user_id)
    return user if user and user.is_active else None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_for_session(db, request.cookies.get(SESSION_COOKIE))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        definition = db.get(RoleDefinition, user.role)
        access_profile = definition.access_profile if definition else user.role
        if access_profile not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")
        return user

    return dependency


def has_permission(user: User, db: Session, permission: str) -> bool:
    definition = db.get(RoleDefinition, user.role)
    if not definition:
        permissions = LEGACY_ROLE_PERMISSIONS.get(user.role, set())
        return "*" in permissions or permission in permissions
    return definition.access_profile == "admin" or "*" in (definition.permissions or []) or permission in (definition.permissions or [])


def require_permission(permission: str):
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if not has_permission(user, db, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permission")
        return user

    return dependency


def websocket_user(websocket: WebSocket, db: Session) -> User | None:
    return user_for_session(db, websocket.cookies.get(SESSION_COOKIE))
