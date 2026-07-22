import os

os.environ["CMH_SMS_DATABASE_URL"] = "sqlite:///./test_serial_management.db"

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.models import Doctor, WaitingRoom


client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    from app.database import SessionLocal
    with SessionLocal() as db:
        db.add(WaitingRoom(id="waiting-room-1", code="WR-1", name="Medicine Waiting Room", floor="2nd Floor", display_label="Waiting Room 1"))
        db.add(Doctor(id="dr-khan", name="Dr. Ayesha Khan", department="Medicine", designation="Consultant", room_number="205", waiting_room_id="waiting-room-1", token_prefix="AK"))
        db.commit()


def token_payload(name="Rahim Uddin"):
    return {
        "patient_name": name,
        "patient_phone": "01700000000",
        "service_category": "army",
        "rank": "Captain",
        "service_number": "BA-TEST-001",
        "doctor_id": "dr-khan",
        "doctor_name": "Dr. Ayesha Khan",
        "department": "Medicine",
        "room_number": "205",
        "waiting_room": "WR-1",
        "source": "walk_in",
        "priority": "normal",
    }


def test_reception_to_display_flow():
    first = client.post("/api/v1/tokens", json=token_payload()).json()
    second = client.post("/api/v1/tokens", json=token_payload("Karim Ahmed")).json()
    assert first["token_number"] == "AK-001"
    assert second["token_number"] == "AK-002"

    called = client.post("/api/v1/doctors/dr-khan/call-next").json()
    assert called["id"] == first["id"]
    assert called["status"] == "called"

    display = client.get("/api/v1/displays/WR-1").json()
    assert display["current"]["patient_name"] == "Rahim U."
    assert len(display["active_calls"]) == 1
    assert display["next_tokens"][0]["patient_name"] == "Karim A."
    assert "room 205" in display["announcement"]


def test_call_and_recall_broadcast_to_all_waiting_rooms():
    created = client.post("/api/v1/tokens", json=token_payload()).json()
    with client.websocket_connect("/api/v1/realtime/waiting-rooms/WR-1") as room_one:
        with client.websocket_connect("/api/v1/realtime/waiting-rooms/WR-2") as room_two:
            room_one.receive_json()
            room_two.receive_json()
            client.post(f"/api/v1/doctors/dr-khan/tokens/{created['id']}/call").raise_for_status()
            for socket in (room_one, room_two):
                called = socket.receive_json()
                assert called["type"] == "patient.called"
                assert called["display"]["current"]["id"] == created["id"]

            client.post(
                f"/api/v1/doctors/dr-khan/tokens/{created['id']}/action",
                json={"action": "recall", "actor": "doctor.test"},
            ).raise_for_status()
            for socket in (room_one, room_two):
                recalled = socket.receive_json()
                assert recalled["type"] == "patient.called"
                assert recalled["reason"] == "queue.recall"
                assert recalled["display"]["current"]["id"] == created["id"]


def test_global_call_remains_visible_when_another_room_refreshes():
    created = client.post("/api/v1/tokens", json=token_payload()).json()
    client.post(f"/api/v1/doctors/dr-khan/tokens/{created['id']}/call").raise_for_status()

    other_room = client.get("/api/v1/displays/WR-3").json()
    assert other_room["current"]["id"] == created["id"]
    assert other_room["next_tokens"] == []


def test_waiting_room_can_hold_calls_for_multiple_doctors():
    from app.database import SessionLocal
    from app.models import Doctor
    with SessionLocal() as db:
        db.add(Doctor(id="dr-rahman", name="Dr. Farhan Rahman", department="Cardiology", designation="Consultant", room_number="312", waiting_room_id="waiting-room-1", token_prefix="FR"))
        db.commit()
    second_payload = token_payload("Nusrat Jahan") | {"doctor_id": "dr-rahman", "doctor_name": "Dr. Farhan Rahman", "department": "Cardiology", "room_number": "312"}
    first = client.post("/api/v1/tokens", json=token_payload()).json()
    second = client.post("/api/v1/tokens", json=second_payload).json()
    client.post(f"/api/v1/doctors/dr-khan/tokens/{first['id']}/call").raise_for_status()
    client.post(f"/api/v1/doctors/dr-rahman/tokens/{second['id']}/call").raise_for_status()
    display = client.get("/api/v1/displays/WR-1").json()
    assert {call["doctor_id"] for call in display["active_calls"]} == {"dr-khan", "dr-rahman"}


def test_doctor_state_transitions_are_validated_and_audited():
    token = client.post("/api/v1/tokens", json=token_payload()).json()
    client.post(f"/api/v1/doctors/dr-khan/tokens/{token['id']}/call").raise_for_status()
    started = client.post(f"/api/v1/doctors/dr-khan/tokens/{token['id']}/action", json={"action": "start", "actor": "doctor.test"}).json()
    assert started["status"] == "in_progress"
    completed = client.post(f"/api/v1/doctors/dr-khan/tokens/{token['id']}/action", json={"action": "complete", "actor": "doctor.test"}).json()
    assert completed["status"] == "completed"
    invalid = client.post(f"/api/v1/doctors/dr-khan/tokens/{token['id']}/action", json={"action": "recall", "actor": "doctor.test"})
    assert invalid.status_code == 409
    actions = [event["action"] for event in client.get("/api/v1/audit").json()]
    assert "queue.start" in actions
    assert "queue.complete" in actions


def test_same_patient_can_be_announced_again_with_recall_limit():
    from app.database import SessionLocal
    from app.models import AppSetting
    with SessionLocal() as db:
        db.add(AppSetting(key="queue", value={"recall_limit": 2}, description="Queue rules"))
        db.commit()
    token = client.post("/api/v1/tokens", json=token_payload()).json()
    client.post(f"/api/v1/doctors/dr-khan/tokens/{token['id']}/call").raise_for_status()
    first = client.post(f"/api/v1/doctors/dr-khan/tokens/{token['id']}/action", json={"action": "recall", "actor": "doctor.test"}).json()
    second = client.post(f"/api/v1/doctors/dr-khan/tokens/{token['id']}/action", json={"action": "recall", "actor": "doctor.test"}).json()
    assert first["recall_count"] == 1
    assert second["recall_count"] == 2
    blocked = client.post(f"/api/v1/doctors/dr-khan/tokens/{token['id']}/action", json={"action": "recall", "actor": "doctor.test"})
    assert blocked.status_code == 409
