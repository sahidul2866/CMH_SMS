"""Expose patient, schedule, and appointment workflow permissions."""

import sqlalchemy as sa

from alembic import op

revision = "20260818_0012"
down_revision = "20260730_0011"
branch_labels = None
depends_on = None

RECEPTION_PERMISSIONS = {
    "pages.appointments",
    "patients.view",
    "patients.manage",
    "appointments.view",
    "appointments.manage",
    "appointments.check_in",
    "schedule.view",
}


def upgrade() -> None:
    roles = sa.table("role_definitions", sa.column("name", sa.String()), sa.column("permissions", sa.JSON()))
    connection = op.get_bind()
    current = connection.execute(sa.select(roles.c.permissions).where(roles.c.name == "reception")).scalar_one_or_none()
    if current is not None:
        connection.execute(
            roles.update()
            .where(roles.c.name == "reception")
            .values(permissions=sorted(set(current) | RECEPTION_PERMISSIONS))
        )


def downgrade() -> None:
    roles = sa.table("role_definitions", sa.column("name", sa.String()), sa.column("permissions", sa.JSON()))
    connection = op.get_bind()
    current = connection.execute(sa.select(roles.c.permissions).where(roles.c.name == "reception")).scalar_one_or_none()
    if current is not None:
        connection.execute(
            roles.update()
            .where(roles.c.name == "reception")
            .values(permissions=sorted(set(current) - RECEPTION_PERMISSIONS))
        )
