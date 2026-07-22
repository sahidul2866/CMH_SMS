"""Add audited queue operations and settings."""
from alembic import op
import sqlalchemy as sa

revision = "20260722_0003"
down_revision = "20260722_0002"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("queue_tokens") as batch:
        batch.add_column(sa.Column("started_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("skipped_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("recalled_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("no_show_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("cancelled_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("recall_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("audit_events",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("action", sa.String(80), nullable=False),
        sa.Column("actor", sa.String(120), nullable=False), sa.Column("token_id", sa.String(36), sa.ForeignKey("queue_tokens.id"), nullable=True),
        sa.Column("previous_status", sa.String(20), nullable=True), sa.Column("new_status", sa.String(20), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True), sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_token_id", "audit_events", ["token_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_table("app_settings",
        sa.Column("key", sa.String(100), primary_key=True), sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(240), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))

def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("audit_events")
    with op.batch_alter_table("queue_tokens") as batch:
        for column in ("recall_count", "cancelled_at", "no_show_at", "recalled_at", "skipped_at", "started_at"):
            batch.drop_column(column)
