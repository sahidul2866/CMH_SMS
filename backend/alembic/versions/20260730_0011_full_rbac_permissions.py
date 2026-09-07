"""Complete production action permissions and defaults."""
import sqlalchemy as sa

from alembic import op

revision = "20260730_0011"
down_revision = "20260730_0010"
branch_labels = None
depends_on = None

ROLE_PERMISSIONS = {
    "admin": ["*"],
    "reception": [
        "pages.reception", "pages.display", "directory.view", "master_data.view",
        "queue.serial.create", "queue.view", "queue.priority", "queue.transfer",
        "queue.print", "display.view",
    ],
    "radiographer": [
        "pages.radiographer", "directory.view", "master_data.view", "queue.view",
        "queue.call", "queue.action", "queue.pause", "audio.announce",
    ],
    "auditor": ["pages.reports", "reports.view"],
    "display": ["pages.display", "directory.view", "display.view"],
}


def upgrade() -> None:
    roles = sa.table("role_definitions", sa.column("name", sa.String()), sa.column("permissions", sa.JSON()))
    for role, permissions in ROLE_PERMISSIONS.items():
        op.get_bind().execute(roles.update().where(roles.c.name == role).values(permissions=permissions))


def downgrade() -> None:
    pass
