from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import SmsMessage

logger = logging.getLogger("uvicorn.error")


class SmsService:
    """Reliable SMS outbox with an optional CMH-approved HTTP gateway."""

    def __init__(self, db: Session):
        self.db = db
        self.gateway_url = os.getenv("CMH_SMS_SMS_GATEWAY_URL", "").strip()
        self.gateway_token = os.getenv("CMH_SMS_SMS_GATEWAY_TOKEN", "").strip()

    def queue(self, mobile: str, message_type: str, body: str) -> SmsMessage | None:
        mobile = mobile.strip()
        if not mobile:
            return None
        item = SmsMessage(mobile=mobile, message_type=message_type, body=body, status="queued")
        self.db.add(item)
        self.db.flush()
        return item

    def dispatch(self, item: SmsMessage) -> SmsMessage:
        if not self.gateway_url:
            return item
        item.attempts += 1
        try:
            headers = {"Authorization": f"Bearer {self.gateway_token}"} if self.gateway_token else {}
            response = httpx.post(
                self.gateway_url,
                json={"to": item.mobile, "message": item.body},
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            item.status = "sent"
            item.provider_reference = str(payload.get("id") or payload.get("message_id") or "") or None
            item.sent_at = datetime.utcnow()
            item.error = None
            item.next_attempt_at = None
        except Exception as exc:
            item.status = "failed"
            item.error = str(exc)[:500]
            item.next_attempt_at = datetime.utcnow() + timedelta(minutes=2 ** max(item.attempts - 1, 0))
        item.claimed_at = None
        self.db.commit()
        return item


class SmsOutboxWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="cmh-sms-outbox")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self._dispatch_batch)
            except Exception:
                logger.exception("SMS outbox batch failed")
            await asyncio.sleep(5)

    @staticmethod
    def _dispatch_batch() -> None:
        with SessionLocal() as db:
            service = SmsService(db)
            if not service.gateway_url:
                return
            now = datetime.utcnow()
            db.execute(
                update(SmsMessage)
                .where(SmsMessage.status == "sending", SmsMessage.claimed_at < now - timedelta(minutes=5))
                .values(status="queued", claimed_at=None)
            )
            messages = list(
                db.scalars(
                    select(SmsMessage)
                    .where(
                        SmsMessage.status.in_(("queued", "failed")),
                        SmsMessage.attempts < 5,
                        or_(SmsMessage.next_attempt_at.is_(None), SmsMessage.next_attempt_at <= now),
                    )
                    .order_by(SmsMessage.created_at)
                    .limit(20)
                    .with_for_update(skip_locked=True)
                )
            )
            for message in messages:
                message.status = "sending"
                message.claimed_at = now
            db.commit()
            for message in messages:
                service.dispatch(message)


sms_outbox_worker = SmsOutboxWorker()
