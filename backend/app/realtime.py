from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import WebSocket


class WaitingRoomHub:
    """Room-scoped WebSocket fan-out for a single API instance."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._sequences: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def connect(self, waiting_room: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[waiting_room].add(websocket)
        await websocket.send_json(self.event(waiting_room, "connection.ready", "connected"))

    async def disconnect(self, waiting_room: str, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._connections.get(waiting_room)
            if not clients:
                return
            clients.discard(websocket)
            if not clients:
                self._connections.pop(waiting_room, None)

    def event(self, waiting_room: str, event_type: str, reason: str, **payload) -> dict:
        self._sequences[waiting_room] += 1
        return {
            "event_id": str(uuid4()),
            "sequence": self._sequences[waiting_room],
            "type": event_type,
            "reason": reason,
            "waiting_room": waiting_room,
            "occurred_at": datetime.now(UTC).isoformat(),
            **payload,
        }

    async def broadcast(self, waiting_room: str, event_type: str, reason: str, **payload) -> None:
        event = self.event(waiting_room, event_type, reason, **payload)
        async with self._lock:
            clients = list(self._connections.get(waiting_room, set()))
        stale: list[WebSocket] = []
        for client in clients:
            try:
                await client.send_json(event)
            except Exception:
                stale.append(client)
        for client in stale:
            await self.disconnect(waiting_room, client)

    async def broadcast_all(self, waiting_room: str, event_type: str, reason: str, **payload) -> None:
        """Send an announcement to every connected waiting-room display."""
        event = self.event(waiting_room, event_type, reason, **payload)
        async with self._lock:
            clients = [
                (room, client)
                for room, room_clients in self._connections.items()
                for client in room_clients
            ]
        stale: list[tuple[str, WebSocket]] = []
        for room, client in clients:
            try:
                await client.send_json(event)
            except Exception:
                stale.append((room, client))
        for room, client in stale:
            await self.disconnect(room, client)

    def connection_count(self, waiting_room: str) -> int:
        return len(self._connections.get(waiting_room, set()))


waiting_room_hub = WaitingRoomHub()
