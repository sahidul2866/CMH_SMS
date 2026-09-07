"""Add holiday calendar required by the PDF SRS."""
import sqlalchemy as sa

from alembic import op

revision = "20260729_0007"
down_revision = "20260729_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holidays",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_holidays_holiday_date", "holidays", ["holiday_date"], unique=True)
    op.create_table(
        "sms_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mobile", sa.String(30), nullable=False),
        sa.Column("message_type", sa.String(30), nullable=False),
        sa.Column("body", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider_reference", sa.String(120), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sms_messages_mobile", "sms_messages", ["mobile"])
    op.create_index("ix_sms_messages_message_type", "sms_messages", ["message_type"])
    op.create_index("ix_sms_messages_status", "sms_messages", ["status"])


def downgrade() -> None:
    op.drop_table("sms_messages")
    op.drop_table("holidays")
