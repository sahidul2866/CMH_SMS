"""Initial standalone CMH Smart Serial schema."""
import sqlalchemy as sa

from alembic import op

revision = "20260722_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("waiting_rooms",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("floor", sa.String(40), nullable=False),
        sa.Column("display_label", sa.String(120), nullable=False),
        sa.Column("audio_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_waiting_rooms_code", "waiting_rooms", ["code"], unique=True)
    op.create_table("doctors",
        sa.Column("id", sa.String(60), primary_key=True), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("department", sa.String(120), nullable=False), sa.Column("designation", sa.String(120), nullable=False),
        sa.Column("room_number", sa.String(30), nullable=False),
        sa.Column("waiting_room_id", sa.String(36), sa.ForeignKey("waiting_rooms.id"), nullable=False),
        sa.Column("token_prefix", sa.String(8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.UniqueConstraint("token_prefix"))
    op.create_index("ix_doctors_waiting_room_id", "doctors", ["waiting_room_id"])
    op.create_table("queue_tokens",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("token_date", sa.Date(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("token_number", sa.String(20), nullable=False),
        sa.Column("patient_name", sa.String(160), nullable=False), sa.Column("patient_phone", sa.String(30), nullable=False),
        sa.Column("doctor_id", sa.String(60), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("doctor_name", sa.String(160), nullable=False), sa.Column("department", sa.String(120), nullable=False),
        sa.Column("room_number", sa.String(30), nullable=False), sa.Column("waiting_room", sa.String(30), nullable=False),
        sa.Column("source", sa.String(20), nullable=False), sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("called_at", sa.DateTime(), nullable=True), sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("token_date", "doctor_id", "sequence", name="uq_daily_doctor_sequence"))
    for name, columns in {"ix_queue_tokens_token_date":["token_date"], "ix_queue_tokens_token_number":["token_number"],
        "ix_queue_tokens_doctor_id":["doctor_id"], "ix_queue_tokens_waiting_room":["waiting_room"],
        "ix_queue_tokens_status":["status"]}.items():
        op.create_index(name, "queue_tokens", columns)

def downgrade() -> None:
    op.drop_table("queue_tokens")
    op.drop_table("doctors")
    op.drop_table("waiting_rooms")
