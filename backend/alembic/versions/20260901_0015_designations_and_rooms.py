"""Make designations and room numbers configurable lookup values."""

from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "20260901_0015"
down_revision = "20260901_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    lookups = sa.table(
        "lookup_options",
        sa.column("id", sa.String()), sa.column("category", sa.String()), sa.column("value", sa.String()),
        sa.column("label", sa.String()), sa.column("sort_order", sa.Integer()), sa.column("metadata_json", sa.JSON()),
        sa.column("is_active", sa.Boolean()), sa.column("created_at", sa.DateTime()), sa.column("updated_at", sa.DateTime()),
    )
    doctors = sa.table("doctors", sa.column("room_number", sa.String()))
    connection = op.get_bind()

    old_designations = connection.execute(
        sa.select(lookups).where(lookups.c.category == "patient_title")
    ).mappings().all()
    existing_designations = set(connection.execute(
        sa.select(lookups.c.value).where(lookups.c.category == "designation")
    ).scalars())
    for item in old_designations:
        if item["value"] in existing_designations:
            connection.execute(lookups.delete().where(lookups.c.id == item["id"]))
        else:
            connection.execute(lookups.update().where(lookups.c.id == item["id"]).values(category="designation"))
            existing_designations.add(item["value"])

    existing_rooms = set(connection.execute(
        sa.select(lookups.c.value).where(lookups.c.category == "room_number")
    ).scalars())
    room_numbers = sorted(set(connection.execute(sa.select(doctors.c.room_number)).scalars()))
    now = datetime.utcnow()
    for index, room_number in enumerate(room_numbers):
        if room_number and room_number not in existing_rooms:
            connection.execute(lookups.insert().values(
                id=str(uuid4()), category="room_number", value=room_number, label=f"Room {room_number}",
                sort_order=index, metadata_json={}, is_active=True, created_at=now, updated_at=now,
            ))


def downgrade() -> None:
    lookups = sa.table("lookup_options", sa.column("category", sa.String()))
    connection = op.get_bind()
    connection.execute(lookups.update().where(lookups.c.category == "designation").values(category="patient_title"))
    connection.execute(lookups.delete().where(lookups.c.category == "room_number"))
