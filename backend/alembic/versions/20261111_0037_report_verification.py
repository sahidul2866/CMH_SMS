"""Record radiologist report verification for each entry."""
from alembic import op
import sqlalchemy as sa

revision = '20261111_0037'
down_revision = '20261110_0036'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('queue_tokens', sa.Column('report_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('queue_tokens', sa.Column('report_verified_at', sa.DateTime(), nullable=True))
    op.add_column('queue_tokens', sa.Column('report_verified_by', sa.String(80), nullable=True))
    op.add_column('queue_tokens', sa.Column('report_radiologist', sa.String(160), nullable=True))
    roles = sa.table('role_definitions', sa.column('name', sa.String), sa.column('permissions', sa.JSON))
    connection = op.get_bind()
    for row in connection.execute(sa.select(roles).where(roles.c.name.in_(['admin', 'radiographer']))).mappings():
        permissions = set(row['permissions'] or [])
        connection.execute(roles.update().where(roles.c.name == row['name']).values(permissions=sorted(permissions | {'reports.verify'})))


def downgrade():
    for column in ('report_radiologist', 'report_verified_by', 'report_verified_at', 'report_verified'):
        op.drop_column('queue_tokens', column)
