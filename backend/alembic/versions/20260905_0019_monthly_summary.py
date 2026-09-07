"""Persist patient/sponsor classification and historical monthly report category."""
import sqlalchemy as sa
from alembic import op

revision = "20260905_0019"
down_revision = "20260905_0018"
branch_labels = None
depends_on = None

FIELDS = ['beneficiary_type', 'service_status', 'entitlement', 'sponsor_rank', 'family_relationship', 'summary_category']

def upgrade():
    with op.batch_alter_table("queue_tokens") as batch:
        for field in FIELDS:
            batch.add_column(sa.Column(field, sa.String(100), nullable=True))

def downgrade():
    with op.batch_alter_table("queue_tokens") as batch:
        for field in reversed(FIELDS):
            batch.drop_column(field)
