"""Add granular permissions to configurable roles."""

import sqlalchemy as sa

from alembic import op

revision = "20260730_0009"
down_revision = "20260730_0008"
branch_labels = None
depends_on = None

ADMIN_PERMISSIONS = [
    "users.view", "users.create", "users.update", "users.delete",
    "users.password.reset", "users.roles.assign",
    "roles.view", "roles.manage",
]


def upgrade() -> None:
    op.add_column(
        "role_definitions",
        sa.Column("permissions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    roles = sa.table("role_definitions", sa.column("name", sa.String()), sa.column("permissions", sa.JSON()))
    op.get_bind().execute(
        roles.update().where(roles.c.name == "admin").values(permissions=ADMIN_PERMISSIONS)
    )


def downgrade() -> None:
    op.drop_column("role_definitions", "permissions")
