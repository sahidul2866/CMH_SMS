"""Replace the four initial radiographer names and room assignments.

Stable IDs preserve account, schedule and patient relationships. Historical
patient snapshots are deliberately retained. Room lookups are additive because
other records may still refer to the previous rooms.
"""
from datetime import datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = '20260926_0024'
down_revision = '20260922_0023'
branch_labels = None
depends_on = None

ROSTER = (
    ('dr-khan', 'Dr. Ayesha Khan', '205', 'SWO Jamil Ahmed', '110'),
    ('dr-rahman', 'Dr. Farhan Rahman', '312', 'WO Hasanuzzaman', '116'),
    ('dr-sultana', 'Dr. Nusrat Sultana', '118', 'SST Md. Delwar Hossain', '104'),
    ('dr-chowdhury', 'Dr. Imran Chowdhury', '407', 'SNK Azim Uddin', '117'),
)


def upgrade():
    connection = op.get_bind()
    doctors = sa.table('doctors', sa.column('id', sa.String), sa.column('name', sa.String), sa.column('room_number', sa.String))
    users = sa.table('users', sa.column('doctor_id', sa.String), sa.column('full_name', sa.String))
    lookups = sa.table('lookup_options',
                       sa.column('id', sa.String), sa.column('category', sa.String), sa.column('value', sa.String),
                       sa.column('label', sa.String), sa.column('sort_order', sa.Integer), sa.column('metadata_json', sa.JSON),
                       sa.column('is_active', sa.Boolean), sa.column('created_at', sa.DateTime), sa.column('updated_at', sa.DateTime))
    now = datetime.utcnow()
    for index, (doctor_id, old_name, old_room, name, room) in enumerate(ROSTER):
        connection.execute(doctors.update().where(doctors.c.id == doctor_id).values(name=name, room_number=room))
        # Preserve account identities and custom display names.
        connection.execute(users.update().where(users.c.doctor_id == doctor_id, users.c.full_name == old_name).values(full_name=name))
        exists = connection.execute(sa.select(lookups.c.id).where(lookups.c.category == 'room_number', lookups.c.value == room)).first()
        if not exists:
            connection.execute(lookups.insert().values(id=str(uuid4()), category='room_number', value=room,
                               label=f'Room {room}', sort_order=index, metadata_json={}, is_active=True,
                               created_at=now, updated_at=now))


def downgrade():
    connection = op.get_bind()
    doctors = sa.table('doctors', sa.column('id', sa.String), sa.column('name', sa.String), sa.column('room_number', sa.String))
    users = sa.table('users', sa.column('doctor_id', sa.String), sa.column('full_name', sa.String))
    for doctor_id, old_name, old_room, name, room in ROSTER:
        # Do not overwrite directory edits made after the migration.
        connection.execute(doctors.update().where(doctors.c.id == doctor_id, doctors.c.name == name,
                           doctors.c.room_number == room).values(name=old_name, room_number=old_room))
        connection.execute(users.update().where(users.c.doctor_id == doctor_id, users.c.full_name == name).values(full_name=old_name))
    # Keep room options: they can now be used by other radiographers or records.
