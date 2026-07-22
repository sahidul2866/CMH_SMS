from __future__ import annotations

from datetime import date

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import AppSetting, AuditEvent, Doctor, QueueToken, WaitingRoom
from .schemas import AuditRead, DashboardRead, DisplayRead, PriorityUpdateRequest, QueueActionRequest, SettingUpdate, TokenCreate, TokenRead
from .service import QueueService
from .realtime import waiting_room_hub


app = FastAPI(title="CMH Smart Serial API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:4300",
        "http://127.0.0.1:4300",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": "cmh-smart-serial"}


@app.get("/api/v1/doctors")
def doctors(db: Session = Depends(get_db)):
    return [
        {"id": item.id, "name": item.name, "department": item.department, "designation": item.designation,
         "room": item.room_number, "waitingRoom": room.code}
        for item, room in db.execute(
            select(Doctor, WaitingRoom).join(WaitingRoom, WaitingRoom.id == Doctor.waiting_room_id)
            .where(Doctor.is_active.is_(True), WaitingRoom.is_active.is_(True)).order_by(Doctor.department, Doctor.name)
        ).all()
    ]


@app.get("/api/v1/waiting-rooms")
def waiting_rooms(db: Session = Depends(get_db)):
    return list(db.scalars(select(WaitingRoom).where(WaitingRoom.is_active.is_(True)).order_by(WaitingRoom.code)))


@app.post("/api/v1/tokens", response_model=TokenRead, status_code=201)
async def create_token(payload: TokenCreate, db: Session = Depends(get_db)):
    service = QueueService(db)
    token = service.create_token(payload)
    state = service.display(token.waiting_room)
    await waiting_room_hub.broadcast(token.waiting_room, "queue.updated", "token.created", display=state.model_dump(mode="json"))
    return token


@app.get("/api/v1/tokens", response_model=list[TokenRead])
def list_tokens(doctor_id: str | None = None, waiting_room: str | None = None, db: Session = Depends(get_db)):
    return QueueService(db).list_tokens(doctor_id, waiting_room)


@app.post("/api/v1/doctors/{doctor_id}/call-next", response_model=TokenRead)
async def call_next(doctor_id: str, db: Session = Depends(get_db)):
    service = QueueService(db)
    token = service.call_next(doctor_id)
    state = service.display(token.waiting_room)
    await waiting_room_hub.broadcast_all(token.waiting_room, "patient.called", "doctor.call_next", display=state.model_dump(mode="json"))
    return token


@app.post("/api/v1/doctors/{doctor_id}/tokens/{token_id}/call", response_model=TokenRead)
async def call_token(doctor_id: str, token_id: str, db: Session = Depends(get_db)):
    service = QueueService(db)
    token = service.call(token_id, doctor_id)
    state = service.display(token.waiting_room)
    await waiting_room_hub.broadcast_all(token.waiting_room, "patient.called", "doctor.manual_call", display=state.model_dump(mode="json"))
    return token


@app.post("/api/v1/doctors/{doctor_id}/tokens/{token_id}/complete", response_model=TokenRead)
async def complete_token(doctor_id: str, token_id: str, db: Session = Depends(get_db)):
    service = QueueService(db)
    token = service.complete(token_id, doctor_id)
    state = service.display(token.waiting_room)
    await waiting_room_hub.broadcast(token.waiting_room, "queue.updated", "consultation.completed", display=state.model_dump(mode="json"))
    return token


@app.post("/api/v1/doctors/{doctor_id}/tokens/{token_id}/action", response_model=TokenRead)
async def queue_action(doctor_id: str, token_id: str, payload: QueueActionRequest, db: Session = Depends(get_db)):
    service = QueueService(db)
    token = service.action(token_id, doctor_id, payload.action, payload.reason, payload.actor)
    state = service.display(token.waiting_room)
    event_type = "patient.called" if payload.action == "recall" else "queue.updated"
    broadcast = waiting_room_hub.broadcast_all if payload.action == "recall" else waiting_room_hub.broadcast
    await broadcast(token.waiting_room, event_type, f"queue.{payload.action}", display=state.model_dump(mode="json"))
    return token


@app.patch("/api/v1/tokens/{token_id}/priority", response_model=TokenRead)
async def update_priority(token_id: str, payload: PriorityUpdateRequest, db: Session = Depends(get_db)):
    service = QueueService(db)
    token = service.update_priority(token_id, payload.priority, payload.reason, payload.actor)
    state = service.display(token.waiting_room)
    await waiting_room_hub.broadcast(token.waiting_room, "queue.updated", "queue.priority_changed", display=state.model_dump(mode="json"))
    return token


@app.get("/api/v1/displays/{waiting_room}", response_model=DisplayRead)
def display(waiting_room: str, db: Session = Depends(get_db)):
    return QueueService(db).display(waiting_room)


@app.websocket("/api/v1/realtime/waiting-rooms/{waiting_room}")
async def waiting_room_realtime(websocket: WebSocket, waiting_room: str):
    await waiting_room_hub.connect(waiting_room, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json(waiting_room_hub.event(waiting_room, "heartbeat", "pong"))
    except WebSocketDisconnect:
        await waiting_room_hub.disconnect(waiting_room, websocket)


@app.get("/api/v1/dashboard", response_model=DashboardRead)
def dashboard(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(QueueToken.status, func.count()).group_by(QueueToken.status)).all())
    return DashboardRead(waiting=counts.get("waiting", 0), called=counts.get("called", 0), completed=counts.get("completed", 0), average_wait_minutes=0)


@app.get("/api/v1/settings")
def settings(db: Session = Depends(get_db)):
    return list(db.scalars(select(AppSetting).order_by(AppSetting.key)))


@app.put("/api/v1/settings/{key}")
def update_setting(key: str, payload: SettingUpdate, db: Session = Depends(get_db)):
    setting = db.get(AppSetting, key)
    if not setting:
        setting = AppSetting(key=key, value=payload.value, description=f"{key.title()} configuration")
        db.add(setting)
    else:
        setting.value = payload.value
    db.commit()
    db.refresh(setting)
    return setting


@app.get("/api/v1/audit", response_model=list[AuditRead])
def audit(limit: int = 100, db: Session = Depends(get_db)):
    return list(db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(min(max(limit, 1), 500))))


@app.get("/api/v1/reports/queue-summary")
def queue_report(db: Session = Depends(get_db)):
    tokens = list(db.scalars(select(QueueToken).where(QueueToken.token_date == date.today())))
    def grouped(field: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for token in tokens:
            key = str(getattr(token, field) or "Unassigned")
            result[key] = result.get(key, 0) + 1
        return result
    return {"total": len(tokens), "by_status": grouped("status"), "by_doctor": grouped("doctor_name"), "by_room": grouped("waiting_room"), "by_source": grouped("source"), "priority": sum(token.priority == "priority" for token in tokens)}
