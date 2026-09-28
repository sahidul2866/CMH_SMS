"""Enable radiographer patient entry and film/contrast updates."""
from alembic import op
import sqlalchemy as sa

revision = '20260928_0034'
down_revision = '20260928_0033'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    roles = sa.table('role_definitions', sa.column('name', sa.String), sa.column('permissions', sa.JSON))
    row = connection.execute(sa.select(roles).where(roles.c.name == 'radiographer')).mappings().first()
    if row:
        connection.execute(roles.update().where(roles.c.name == 'radiographer').values(
            permissions=sorted(set(row['permissions'] or []) | {'pages.reception', 'queue.serial.create', 'queue.supplies.update'})))


def downgrade():
    pass
