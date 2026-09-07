from __future__ import annotations

import asyncio
import atexit
import os
import sys
import threading
from pathlib import Path
from typing import Iterable

from a2wsgi import ASGIMiddleware

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def load_environment(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_environment(BASE_DIR / ".env")

from app.main import app  # noqa: E402

_adapter: ASGIMiddleware | None = None
_adapter_pid: int | None = None
_lifespan_context: object | None = None
_adapter_lock = threading.Lock()


def _shutdown_adapter() -> None:
    global _lifespan_context
    if _adapter is None or _adapter_pid != os.getpid() or _lifespan_context is None:
        return
    try:
        future = asyncio.run_coroutine_threadsafe(_lifespan_context.__aexit__(None, None, None), _adapter.loop)
        future.result(timeout=30)
    finally:
        _lifespan_context = None


def _ensure_adapter() -> ASGIMiddleware:
    global _adapter, _adapter_pid, _lifespan_context
    process_id = os.getpid()
    if _adapter is not None and _adapter_pid == process_id:
        return _adapter
    with _adapter_lock:
        if _adapter is not None and _adapter_pid == process_id:
            return _adapter
        _adapter = ASGIMiddleware(app, wait_time=60)
        _adapter_pid = process_id
        _lifespan_context = app.router.lifespan_context(app)
        future = asyncio.run_coroutine_threadsafe(_lifespan_context.__aenter__(), _adapter.loop)
        try:
            future.result(timeout=60)
        except Exception:
            _adapter = None
            _adapter_pid = None
            _lifespan_context = None
            raise
        return _adapter


atexit.register(_shutdown_adapter)


def application(environ: dict, start_response: object) -> Iterable[bytes]:
    """Expose FastAPI as WSGI and initialize the event loop after worker fork."""
    return _ensure_adapter()(environ, start_response)
