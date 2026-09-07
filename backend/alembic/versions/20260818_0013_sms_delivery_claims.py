"""Add durable SMS delivery claiming and retry scheduling."""

import sqlalchemy as sa

from alembic import op

revision = "20260818_0013"
down_revision = "20260818_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sms_messages", sa.Column("next_attempt_at", sa.DateTime(), nullable=True))
    op.add_column("sms_messages", sa.Column("claimed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_sms_messages_next_attempt_at", "sms_messages", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_sms_messages_next_attempt_at", table_name="sms_messages")
    op.drop_column("sms_messages", "claimed_at")
    op.drop_column("sms_messages", "next_attempt_at")
