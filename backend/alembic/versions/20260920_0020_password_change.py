"""Require password changes after administrator resets."""
from alembic import op
import sqlalchemy as sa

revision = '20260920_0020'
down_revision = '20260905_0019'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('users', 'must_change_password')
