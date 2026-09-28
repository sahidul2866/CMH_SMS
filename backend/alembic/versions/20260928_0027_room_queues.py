"""Convert directory entries to room queues without breaking existing references."""
from alembic import op
import sqlalchemy as sa

revision = '20260928_0027'
down_revision = '20260926_0026'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    rooms = sa.table('doctors', sa.column('id', sa.String), sa.column('name', sa.String),
                     sa.column('room_number', sa.String))
    # Keep stable queue IDs so accounts, schedules and patient history remain linked.
    for room in connection.execute(sa.select(rooms)).mappings():
        connection.execute(rooms.update().where(rooms.c.id == room['id']).values(name=f"Room {room['room_number']}"))


def downgrade():
    # Staff names cannot be inferred from room queues.
    pass
