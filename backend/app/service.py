from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import AppSetting, AuditEvent, Doctor, QueueToken
from .schemas import DisplayRead, TokenCreate, TokenRead


ACTIVE_STATUSES = ("waiting", "called")


class QueueService:
    def __init__(self, db: Session):
        self.db = db

    def create_token(self, payload: TokenCreate) -> TokenRead:
        sequence = self.db.scalar(
            select(func.coalesce(func.max(QueueToken.sequence), 0)).where(
                QueueToken.token_date == date.today(), QueueToken.doctor_id == payload.doctor_id
            )
        ) + 1
        doctor = self.db.get(Doctor, payload.doctor_id)
        if not doctor or not doctor.is_active:
            raise HTTPException(404, "Doctor not found or inactive")
        token = QueueToken(
            **payload.model_dump(), token_date=date.today(), sequence=sequence,
            token_number=f"{doctor.token_prefix}-{sequence:03d}"
        )
        self.db.add(token)
        self._audit(token, "token.created", "reception.operator", None, "waiting", detail={"source": token.source, "waiting_room": token.waiting_room})
        self.db.commit()
        return self._read(token)

    def list_tokens(self, doctor_id: str | None = None, waiting_room: str | None = None) -> list[TokenRead]:
        stmt = select(QueueToken).where(QueueToken.token_date == date.today())
        if doctor_id:
            stmt = stmt.where(QueueToken.doctor_id == doctor_id)
        if waiting_room:
            stmt = stmt.where(QueueToken.waiting_room == waiting_room)
        stmt = stmt.order_by(
            case((QueueToken.status == "called", 0), (QueueToken.status == "waiting", 1), else_=2),
            case((QueueToken.priority == "priority", 0), else_=1),
            QueueToken.sequence,
        )
        return [self._read(token) for token in self.db.scalars(stmt)]

    def call_next(self, doctor_id: str) -> TokenRead:
        token = self.db.scalar(
            select(QueueToken).where(
                QueueToken.token_date == date.today(),
                QueueToken.doctor_id == doctor_id,
                QueueToken.status == "waiting",
            ).order_by(case((QueueToken.priority == "priority", 0), else_=1), QueueToken.sequence).limit(1)
        )
        if not token:
            raise HTTPException(404, "No waiting patient found")
        return self.call(token.id, doctor_id, action_name="doctor.call_next")

    def call(self, token_id: str, doctor_id: str, *, action_name: str = "doctor.manual_call") -> TokenRead:
        token = self._get(token_id, doctor_id)
        if token.status not in {"waiting", "called"}:
            raise HTTPException(409, "Only waiting or called tokens can be called")
        current = self.db.scalars(
            select(QueueToken).where(
                QueueToken.token_date == date.today(), QueueToken.doctor_id == doctor_id,
                QueueToken.status == "called", QueueToken.id != token.id,
            )
        )
        for previous in current:
            previous.status = "waiting"
            previous.called_at = None
        previous_status = token.status
        token.status = "called"
        token.called_at = datetime.utcnow()
        self._audit(token, action_name, doctor_id, previous_status, "called", detail={"waiting_room": token.waiting_room})
        self.db.commit()
        return self._read(token)

    def complete(self, token_id: str, doctor_id: str) -> TokenRead:
        return self.action(token_id, doctor_id, "complete", None, doctor_id)

    def action(self, token_id: str, doctor_id: str, action: str, reason: str | None, actor: str) -> TokenRead:
        token = self._get(token_id, doctor_id)
        transitions = {
            "start": ({"called", "recalled"}, "in_progress"),
            "complete": ({"in_progress"}, "completed"),
            "skip": ({"called", "recalled"}, "skipped"),
            "recall": ({"skipped", "called", "recalled"}, "recalled"),
            "no_show": ({"called", "recalled", "skipped"}, "no_show"),
            "cancel": ({"waiting", "skipped", "in_progress"}, "cancelled"),
        }
        allowed, new_status = transitions[action]
        if token.status not in allowed:
            raise HTTPException(409, f"Cannot {action.replace('_', ' ')} a token in {token.status} state")
        if action in {"skip", "no_show", "cancel"} and not reason:
            raise HTTPException(422, "A reason is required for this action")
        previous_status = token.status
        if action == "recall":
            queue_setting = self.db.get(AppSetting, "queue")
            recall_limit = int((queue_setting.value if queue_setting else {}).get("recall_limit", 3))
            if token.recall_count >= recall_limit:
                raise HTTPException(409, f"Recall limit of {recall_limit} has been reached")
        token.status = new_status
        now = datetime.utcnow()
        timestamp_fields = {"start": "started_at", "complete": "completed_at", "skip": "skipped_at", "recall": "recalled_at", "no_show": "no_show_at", "cancel": "cancelled_at"}
        setattr(token, timestamp_fields[action], now)
        if action == "recall":
            token.recall_count += 1
            token.called_at = now
        self._audit(token, f"queue.{action}", actor, previous_status, new_status, reason=reason, detail={"doctor_id": doctor_id, "waiting_room": token.waiting_room})
        self.db.commit()
        return self._read(token)

    def update_priority(self, token_id: str, priority: str, reason: str, actor: str) -> TokenRead:
        token = self.db.get(QueueToken, token_id)
        if not token or token.token_date != date.today():
            raise HTTPException(404, "Queue token not found")
        previous = token.priority
        token.priority = priority
        self._audit(token, "queue.priority_changed", actor, token.status, token.status, reason=reason, detail={"previous_priority": previous, "new_priority": priority})
        self.db.commit()
        return self._read(token)

    def display(self, waiting_room: str) -> DisplayRead:
        room_tokens = self.list_tokens(waiting_room=waiting_room)
        all_tokens = self.list_tokens()
        active_calls = sorted(
            (token for token in all_tokens if token.status in {"called", "recalled"}),
            key=lambda token: token.called_at or token.created_at,
            reverse=True,
        )
        current = active_calls[0] if active_calls else None
        display_setting = self.db.get(AppSetting, "display")
        values = display_setting.value if display_setting else {}
        next_count = max(1, min(int(values.get("next_token_count", 5)), 10))
        upcoming = [token for token in room_tokens if token.status == "waiting"][:next_count]
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
                    doctor_name = doctor_name[len(prefix):].strip()
                    break
            announcement = (
                f"Token {current.token_number}, {current.patient_name}. Please proceed to "
                f"Doctor {doctor_name}, room {current.room_number}."
            )
        return DisplayRead(waiting_room=waiting_room, current=current, active_calls=active_calls, next_tokens=upcoming, announcement=announcement)

    def _audit(self, token: QueueToken, action: str, actor: str, previous_status: str | None, new_status: str | None, *, reason: str | None = None, detail: dict | None = None) -> None:
        self.db.add(AuditEvent(action=action, actor=actor, token_id=token.id, previous_status=previous_status, new_status=new_status, reason=reason, detail=detail or {}))

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
        token = self.db.get(QueueToken, token_id)
        if not token or token.token_date != date.today() or token.doctor_id != doctor_id:
            raise HTTPException(404, "Queue token not found")
        return token

    @staticmethod
    def _doctor_prefix(name: str) -> str:
        letters = "".join(part[0] for part in name.replace(".", "").split() if part.lower() not in {"dr", "doctor"})
        return (letters[:2] or "D").upper()

    @staticmethod
    def _read(token: QueueToken) -> TokenRead:
        now = datetime.utcnow()
        waiting_minutes = max(int((now - token.created_at).total_seconds() // 60), 0)
        return TokenRead.model_validate(token).model_copy(update={"waiting_minutes": waiting_minutes})
