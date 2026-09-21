"""Persist configurable registration values without per-field schema changes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '20260921_0021'
down_revision = '20260920_0020'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('queue_tokens', sa.Column('custom_fields', sa.JSON().with_variant(JSONB(), 'postgresql'), nullable=False, server_default='{}'))


def downgrade():
    op.drop_column('queue_tokens', 'custom_fields')
