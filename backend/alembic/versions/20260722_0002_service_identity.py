"""Add armed-forces service identity to queue registration."""
import sqlalchemy as sa

from alembic import op

revision = "20260722_0002"
down_revision = "20260722_0001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table("queue_tokens") as batch:
        batch.add_column(sa.Column("service_category", sa.String(30), nullable=False, server_default="civilian"))
        batch.add_column(sa.Column("rank", sa.String(60), nullable=True))
        batch.add_column(sa.Column("service_number", sa.String(40), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table("queue_tokens") as batch:
        batch.drop_column("service_number")
        batch.drop_column("rank")
        batch.drop_column("service_category")
