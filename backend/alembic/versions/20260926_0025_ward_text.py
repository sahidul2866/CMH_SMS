"""Store ward details and index sponsor service-number searches."""
from alembic import op
import sqlalchemy as sa

revision = '20260926_0025'
down_revision = '20260926_0024'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('queue_tokens', sa.Column('ward_text', sa.String(240), nullable=True))
    op.create_index('ix_queue_tokens_service_number', 'queue_tokens', ['service_number'])


def downgrade():
    op.drop_index('ix_queue_tokens_service_number', table_name='queue_tokens')
    op.drop_column('queue_tokens', 'ward_text')
