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
            clients = [(room, client) for room, room_clients in self._connections.items() for client in room_clients]
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


def mutation_topics(method: str, path: str, status_code: int) -> list[str]:
    """Publish invalidation hints only after successful, relevant writes."""
    if method not in {'POST', 'PUT', 'PATCH', 'DELETE'} or not 200 <= status_code < 300:
        return []
    prefix = '/api/v1/'
    if not path.startswith(prefix):
        return []
    route = path[len(prefix):].strip('/')
    if route == 'tokens' or route.startswith(('tokens/', 'doctors/')):
        return ['queue']
    if route.startswith('appointments/') and route.endswith('/check-in'):
        return ['queue']
    if route.startswith(('admin/doctors', 'admin/waiting-rooms')):
        return ['directory', 'queue']
    if route == 'lookups' or route.startswith('lookups/'):
        return ['lookups', 'queue']
    if route == 'registration-fields':
        return ['registration']
    if route in {'settings/display', 'settings/queue'}:
        return ['queue']
    if route in {'users', 'roles'} or route.startswith(('users/', 'roles/')):
        return ['access']
    return []


class ChangeHub(WaitingRoomHub):
    """Patient-free invalidation channel; clients refetch through scoped APIs."""

    async def publish(self, topics: list[str]) -> None:
        event = self.event('application', 'data.changed', 'updated', topics=topics)
        async with self._lock:
            clients = list(self._connections.get('application', set()))

        async def send(client: WebSocket) -> None:
            try:
                await asyncio.wait_for(client.send_json(event), timeout=2)
            except Exception:
                await self.disconnect('application', client)
                try:
                    await asyncio.wait_for(client.close(code=1013), timeout=1)
                except Exception:
                    pass

        await asyncio.gather(*(send(client) for client in clients))


change_hub = ChangeHub()
