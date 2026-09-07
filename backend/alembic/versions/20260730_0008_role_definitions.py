"""Add configurable RBAC role definitions."""
import sqlalchemy as sa

from alembic import op

revision = "20260730_0008"
down_revision = "20260729_0007"
branch_labels = None
depends_on = None

ROLES = (
    ("admin", "Administrator", "admin", "Full system administration"),
    ("reception", "Reception", "reception", "Direct patient serial registration and queue management"),
    ("radiographer", "Radiographer", "radiographer", "Assigned clinical queue"),
    ("auditor", "Auditor", "auditor", "Reports and audit records"),
    ("display", "Display", "display", "Waiting-room display"),
)

def upgrade() -> None:
    table = op.create_table(
        "role_definitions",
        sa.Column("name", sa.String(30), primary_key=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("access_profile", sa.String(30), nullable=False),
        sa.Column("description", sa.String(240), nullable=False, server_default=""),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_role_definitions_access_profile", "role_definitions", ["access_profile"])
    op.bulk_insert(table, [
        {"name": name, "display_name": label, "access_profile": profile, "description": description, "is_system": True}
        for name, label, profile, description in ROLES
    ])

def downgrade() -> None:
    op.drop_table("role_definitions")
