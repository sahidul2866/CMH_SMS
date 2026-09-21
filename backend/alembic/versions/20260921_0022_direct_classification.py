"""Keep directly chosen report categories across unrelated patient edits."""
from alembic import op
import sqlalchemy as sa

revision = '20260921_0022'
down_revision = '20260921_0021'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('queue_tokens', sa.Column('summary_category_source', sa.String(20), nullable=False, server_default='automatic'))


def downgrade():
    op.drop_column('queue_tokens', 'summary_category_source')
