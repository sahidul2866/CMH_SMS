"""Bounded structured diagnostics, separate from the clinical audit database."""
from __future__ import annotations

import contextvars
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import threading
import traceback
from datetime import datetime, timezone

request_id_context = contextvars.ContextVar('request_id', default=None)
logger = logging.getLogger('cmh')
_config_lock = threading.Lock()
_audit_installed = False
REDACTED_KEYS = {'password', 'new_password', 'current_password', 'authorization', 'cookie', 'cookies',
                 'token', 'session', 'secret', 'patient_name', 'patient_name_bn', 'patient_phone',
                 'service_number', 'body', 'query', 'detail', 'reason', 'database_url'}


def safe_fields(value):
    if isinstance(value, dict):
        return {str(key): '[redacted]' if any(part in str(key).lower() for part in REDACTED_KEYS)
                else safe_fields(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_fields(item) for item in value[:50]]
    if isinstance(value, str):
        return value[:1000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return type(value).__name__


class JsonLogFormatter(logging.Formatter):
    def format(self, record):
        fields = safe_fields(getattr(record, 'fields', {}))
        entry = {
            'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            'level': record.levelname,
            'event': record.getMessage(),
            'request_id': getattr(record, 'request_id', None) or request_id_context.get(),
            **fields,
        }
        if record.exc_info and record.exc_info[1]:
            # Exception messages, SQL parameters and local variables may contain
            # patient data or credentials. Keep actionable locations and types.
            entry['error_type'] = type(record.exc_info[1]).__name__
            entry['traceback'] = [
                {'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name}
                for frame in traceback.extract_tb(record.exc_info[2])[-25:]
            ]
        return json.dumps(entry, ensure_ascii=False, separators=(',', ':'))


class PrivateRotatingFileHandler(RotatingFileHandler):
    def _open(self):
        stream = super()._open()
        try:
            os.chmod(self.baseFilename, 0o600)
        except OSError:
            pass
        return stream


def configure_logging() -> Path:
    directory = Path(os.getenv('CMH_SMS_LOG_DIR', str(Path(__file__).resolve().parents[1] / 'data' / 'logs')))
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / 'application.jsonl'
    level = os.getenv('CMH_SMS_LOG_LEVEL', 'INFO').upper()
    if level not in {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}:
        level = 'INFO'
    with _config_lock:
        if not any(isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == target.resolve() for handler in logger.handlers):
            handler = PrivateRotatingFileHandler(target, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
            handler.setFormatter(JsonLogFormatter())
            logger.addHandler(handler)
            try:
                target.chmod(0o600)
            except OSError:
                pass
        logger.setLevel(level)
        logger.propagate = False
    return target


def log_event(event: str, *, level: int = logging.INFO, error: BaseException | None = None, **fields) -> None:
    logger.log(level, event, extra={'fields': fields, 'request_id': request_id_context.get()},
               exc_info=(type(error), error, error.__traceback__) if error else None)


def install_audit_logging() -> None:
    """Mirror committed audit metadata; never log rolled-back actions or details."""
    global _audit_installed
    if _audit_installed:
        return
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from .models import AuditEvent

    @event.listens_for(Session, 'after_flush')
    def collect(session, _context):
        pending = session.info.setdefault('_diagnostic_audit', [])
        for row in session.new:
            if isinstance(row, AuditEvent):
                pending.append((session.get_nested_transaction(), {
                    'audit_id': row.id, 'action': row.action, 'actor': row.actor,
                    'previous_status': row.previous_status, 'new_status': row.new_status,
                }))

    @event.listens_for(Session, 'after_commit')
    def committed(session):
        if session.in_nested_transaction():
            return
        for _transaction, fields in session.info.pop('_diagnostic_audit', []):
            log_event('audit.committed', **fields)

    @event.listens_for(Session, 'after_soft_rollback')
    def rolled_back(session, previous_transaction):
        if previous_transaction.nested:
            session.info['_diagnostic_audit'] = [(transaction, fields) for transaction, fields in session.info.get('_diagnostic_audit', []) if transaction is not previous_transaction]
        elif previous_transaction.parent is None:
            session.info.pop('_diagnostic_audit', None)

    _audit_installed = True
