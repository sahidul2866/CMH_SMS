"""Seed page and queue-action permissions for system roles."""
import sqlalchemy as sa

from alembic import op

revision = "20260730_0010"
down_revision = "20260730_0009"
branch_labels = None
depends_on = None

ROLE_PERMISSIONS = {
    "admin": ["*"],
    "reception": [
        "pages.reception", "pages.display", "queue.serial.create", "queue.view",
        "queue.priority", "queue.transfer", "display.view",
    ],
    "radiographer": [
        "pages.radiographer", "queue.view", "queue.call", "queue.action",
    ],
    "auditor": ["pages.reports", "reports.view"],
    "display": ["pages.display", "display.view"],
}


def upgrade() -> None:
    roles = sa.table("role_definitions", sa.column("name", sa.String()), sa.column("permissions", sa.JSON()))
    for role, permissions in ROLE_PERMISSIONS.items():
        op.get_bind().execute(roles.update().where(roles.c.name == role).values(permissions=permissions))


def downgrade() -> None:
    roles = sa.table("role_definitions", sa.column("name", sa.String()), sa.column("permissions", sa.JSON()))
    op.get_bind().execute(roles.update().where(roles.c.name != "admin").values(permissions=[]))
