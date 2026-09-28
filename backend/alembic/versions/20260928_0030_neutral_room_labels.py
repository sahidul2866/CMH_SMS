"""Remove legacy demo specialties from room and waiting-area labels."""
from alembic import op
import sqlalchemy as sa

revision = '20260928_0030'
down_revision = '20260928_0029'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    waiting = sa.table('waiting_rooms', sa.column('id', sa.String), sa.column('name', sa.String),
                       sa.column('display_label', sa.String))
    legacy = [('Medicine Waiting Room', 'Medicine & General'), ('Cardiology Waiting Room', 'Cardiology'),
              ('Paediatrics Waiting Room', 'Paediatrics'), ('Orthopaedics Waiting Room', 'Orthopaedics')]
    for index, (name, label) in enumerate(legacy, 1):
        neutral = f'Waiting Room {index}'
        connection.execute(waiting.update().where(waiting.c.id == f'waiting-room-{index}',
                           waiting.c.name == name).values(name=neutral))
        connection.execute(waiting.update().where(waiting.c.id == f'waiting-room-{index}',
                           waiting.c.display_label == label).values(display_label=neutral))
    rooms = sa.table('doctors', sa.column('id', sa.String), sa.column('department', sa.String))
    for room_id, department in zip(('dr-khan', 'dr-rahman', 'dr-sultana', 'dr-chowdhury'),
                                   ('Medicine', 'Cardiology', 'Paediatrics', 'Orthopaedics')):
        connection.execute(rooms.update().where(rooms.c.id == room_id, rooms.c.department == department)
                           .values(department='Radiology'))


def downgrade():
    # Do not restore demo labels over administrator settings.
    pass
