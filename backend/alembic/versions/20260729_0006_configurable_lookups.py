"""Add configurable form lookup values and patient titles."""
import sqlalchemy as sa

from alembic import op

revision = "20260729_0006"
down_revision = "20260729_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lookup_options",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("value", sa.String(80), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("category", "value", name="uq_lookup_category_value"),
    )
    op.create_index("ix_lookup_options_category", "lookup_options", ["category"])
    with op.batch_alter_table("patients") as batch:
        batch.add_column(sa.Column("title", sa.String(30), nullable=True))
    with op.batch_alter_table("queue_tokens") as batch:
        batch.add_column(sa.Column("patient_title", sa.String(30), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("queue_tokens") as batch:
        batch.drop_column("patient_title")
    with op.batch_alter_table("patients") as batch:
        batch.drop_column("title")
    op.drop_table("lookup_options")
