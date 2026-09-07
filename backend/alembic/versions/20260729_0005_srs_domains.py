"""Add patients, appointments, schedules, controls, devices and call events."""
import sqlalchemy as sa

from alembic import op

revision = "20260729_0005"
down_revision = "20260727_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_number", sa.String(30), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("mobile", sa.String(30), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("sex", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_patients_patient_number", "patients", ["patient_number"], unique=True)
    op.create_index("ix_patients_name", "patients", ["name"])
    op.create_index("ix_patients_mobile", "patients", ["mobile"])
    op.create_table(
        "schedule_slots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("doctor_id", sa.String(60), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("doctor_id", "starts_at", name="uq_doctor_slot_start"),
    )
    op.create_index("ix_schedule_slots_doctor_id", "schedule_slots", ["doctor_id"])
    op.create_index("ix_schedule_slots_starts_at", "schedule_slots", ["starts_at"])
    op.create_table(
        "appointments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("appointment_number", sa.String(30), nullable=False),
        sa.Column("patient_id", sa.String(36), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("doctor_id", sa.String(60), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("slot_id", sa.String(36), sa.ForeignKey("schedule_slots.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(240), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("checked_in_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_appointments_appointment_number", "appointments", ["appointment_number"], unique=True)
    op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"])
    op.create_index("ix_appointments_doctor_id", "appointments", ["doctor_id"])
    op.create_index("ix_appointments_slot_id", "appointments", ["slot_id"])
    op.create_index("ix_appointments_status", "appointments", ["status"])
    with op.batch_alter_table("queue_tokens") as batch:
        batch.add_column(sa.Column("patient_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("appointment_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("scheduled_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key("fk_queue_token_patient", "patients", ["patient_id"], ["id"])
        batch.create_foreign_key("fk_queue_token_appointment", "appointments", ["appointment_id"], ["id"])
        batch.create_index("ix_queue_tokens_patient_id", ["patient_id"])
        batch.create_index("ix_queue_tokens_appointment_id", ["appointment_id"], unique=True)
    op.create_table(
        "queue_controls",
        sa.Column("doctor_id", sa.String(60), sa.ForeignKey("doctors.id"), primary_key=True),
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.String(240), nullable=True),
        sa.Column("updated_by", sa.String(120), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "device_endpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("device_type", sa.String(20), nullable=False),
        sa.Column("waiting_room", sa.String(30), nullable=False),
        sa.Column("client_key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("last_event_id", sa.String(36), nullable=True),
        sa.Column("last_acknowledged_event_id", sa.String(36), nullable=True),
        sa.Column("fault", sa.String(240), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_device_endpoints_device_type", "device_endpoints", ["device_type"])
    op.create_index("ix_device_endpoints_waiting_room", "device_endpoints", ["waiting_room"])
    op.create_table(
        "call_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_id", sa.String(36), sa.ForeignKey("queue_tokens.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("waiting_room", sa.String(30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_call_events_token_id", "call_events", ["token_id"])
    op.create_index("ix_call_events_waiting_room", "call_events", ["waiting_room"])
    op.create_index("ix_call_events_created_at", "call_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("call_events")
    op.drop_table("device_endpoints")
    op.drop_table("queue_controls")
    with op.batch_alter_table("queue_tokens") as batch:
        batch.drop_index("ix_queue_tokens_appointment_id")
        batch.drop_index("ix_queue_tokens_patient_id")
        batch.drop_column("scheduled_at")
        batch.drop_column("appointment_id")
        batch.drop_column("patient_id")
    op.drop_table("appointments")
    op.drop_table("schedule_slots")
    op.drop_table("patients")
