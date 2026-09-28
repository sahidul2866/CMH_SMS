"""Use assigned room numbers as radiographer login IDs, preserving credentials."""
import re
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = '20260928_0032'
down_revision = '20260928_0031'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    users = sa.table('users', sa.column('id', sa.String), sa.column('username', sa.String),
                     sa.column('role', sa.String), sa.column('doctor_id', sa.String))
    rooms = sa.table('doctors', sa.column('id', sa.String), sa.column('room_number', sa.String))
    roles = sa.table('role_definitions', sa.column('name', sa.String), sa.column('access_profile', sa.String))
    profiles = dict(connection.execute(sa.select(roles.c.name, roles.c.access_profile)).all())
    room_numbers = dict(connection.execute(sa.select(rooms.c.id, rooms.c.room_number)).all())
    accounts = connection.execute(sa.select(users).order_by(users.c.username, users.c.id)).mappings().all()
    assignments = {}
    for account in accounts:
        if profiles.get(account['role'], account['role']) != 'radiographer' or account['doctor_id'] not in room_numbers:
            continue
        username = re.sub(r'[^a-z0-9._-]+', '-', room_numbers[account['doctor_id']].strip().lower()).strip('-')
        if not username:
            raise RuntimeError('Assigned room needs a valid room-number user ID')
        if username in assignments.values():
            raise RuntimeError(f'Room {username} has multiple accounts. Reassign or remove the duplicate account before migrating.')
        assignments[account['id']] = username
    occupied = {account['username'] for account in accounts if account['id'] not in assignments}
    collisions = occupied.intersection(assignments.values())
    if collisions:
        raise RuntimeError('Room user IDs already belong to other accounts: ' + ', '.join(sorted(collisions)))
    # All checks precede writes. Temporary IDs allow room usernames to swap safely.
    for account_id in assignments:
        connection.execute(users.update().where(users.c.id == account_id).values(username=f'_room_migration_{uuid4().hex}'))
    for account_id, username in assignments.items():
        connection.execute(users.update().where(users.c.id == account_id).values(username=username))


def downgrade():
    # Old personal login names cannot be reconstructed safely.
    pass
