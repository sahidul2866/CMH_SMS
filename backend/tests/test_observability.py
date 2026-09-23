import io
import json
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.observability import JsonLogFormatter, install_audit_logging, logger, log_event, request_id_context


def capture():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    return stream, handler


def test_diagnostics_redact_sensitive_fields_and_exception_messages():
    stream, handler = capture()
    context = request_id_context.set('test-request')
    try:
        try:
            raise ValueError('private patient secret')
        except ValueError as error:
            log_event('test.failure', error=error, patient_name='Private Name', password='private password', nested={'service_number': '123'})
        row = json.loads(stream.getvalue())
        assert row['request_id'] == 'test-request'
        assert row['error_type'] == 'ValueError'
        assert row['traceback'][0]['function'] == 'test_diagnostics_redact_sensitive_fields_and_exception_messages'
        assert row['patient_name'] == '[redacted]'
        assert 'private' not in stream.getvalue().lower()
    finally:
        logger.removeHandler(handler)
        request_id_context.reset(context)


def test_audit_only_logs_committed_actions_and_omits_details():
    install_audit_logging()
    engine = create_engine('sqlite://')
    AuditEvent.__table__.create(engine)
    stream, handler = capture()
    try:
        with Session(engine) as db:
            db.add(AuditEvent(action='discarded', actor='staff', detail={'patient_name': 'Secret'}))
            db.flush()
            db.rollback()
            db.add(AuditEvent(action='saved', actor='staff', detail={'patient_name': 'Secret'}))
            with db.begin_nested() as nested:
                db.add(AuditEvent(action='nested_discarded', actor='staff'))
                db.flush()
                nested.rollback()
            db.commit()
        rows = [json.loads(line) for line in stream.getvalue().splitlines()]
        assert [row['action'] for row in rows] == ['saved']
        assert 'Secret' not in stream.getvalue()
    finally:
        logger.removeHandler(handler)
        engine.dispose()
