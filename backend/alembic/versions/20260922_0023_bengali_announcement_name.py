"""Save an editable Bengali name for single-voice announcements."""
from alembic import op
import sqlalchemy as sa

revision = '20260922_0023'
down_revision = '20260921_0022'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('queue_tokens', sa.Column('patient_name_bn', sa.String(480), nullable=True))


def downgrade():
    op.drop_column('queue_tokens', 'patient_name_bn')
