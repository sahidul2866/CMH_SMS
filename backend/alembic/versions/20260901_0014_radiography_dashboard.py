"""Add the role-scoped radiography dashboard and head role."""

import sqlalchemy as sa

from alembic import op

revision = "20260901_0014"
down_revision = "20260818_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    roles = sa.table(
        "role_definitions",
        sa.column("name", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("access_profile", sa.String()),
        sa.column("description", sa.String()),
        sa.column("permissions", sa.JSON()),
        sa.column("is_system", sa.Boolean()),
    )
    connection = op.get_bind()
    radiographer = connection.execute(
        sa.select(roles.c.permissions).where(roles.c.name == "radiographer")
    ).scalar_one_or_none()
    if radiographer is not None:
        permissions = list(dict.fromkeys([*radiographer, "pages.dashboard", "dashboard.view"]))
        connection.execute(roles.update().where(roles.c.name == "radiographer").values(permissions=permissions))
    auditor = connection.execute(
        sa.select(roles.c.permissions).where(roles.c.name == "auditor")
    ).scalar_one_or_none()
    if auditor is not None:
        permissions = list(dict.fromkeys([*auditor, "pages.dashboard", "dashboard.view"]))
        connection.execute(roles.update().where(roles.c.name == "auditor").values(permissions=permissions))
    connection.execute(
        roles.insert().values(
            name="radiography_head",
            display_name="Radiography Head",
            access_profile="reception",
            description="Department-wide radiography operational oversight",
            permissions=[
                "pages.dashboard", "pages.radiographer", "pages.reports", "dashboard.view", "reports.view",
                "directory.view", "master_data.view", "queue.view",
            ],
            is_system=True,
        )
    )


def downgrade() -> None:
    roles = sa.table("role_definitions", sa.column("name", sa.String()))
    op.get_bind().execute(roles.delete().where(roles.c.name == "radiography_head"))
