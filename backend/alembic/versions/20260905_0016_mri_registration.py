"""Persist MRI registration details and annual serial counters."""
from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision = "20260905_0016"
down_revision = "20260901_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("registration_counters", sa.Column("year", sa.Integer(), primary_key=True),
                    sa.Column("sequence", sa.Integer(), nullable=False))
    with op.batch_alter_table("queue_tokens") as batch:
        for name, kind in [("serial_number", sa.String(30)), ("age", sa.Integer()),
                           ("unit", sa.String(160)), ("mri_area", sa.String(240)),
                           ("contrast", sa.Integer()), ("film", sa.Integer()),
                           ("report", sa.Text()), ("patient_source", sa.String(100))]:
            batch.add_column(sa.Column(name, kind, nullable=True))
        batch.create_unique_constraint("uq_registration_serial", ["serial_number"])
    table = sa.table("lookup_options", sa.column("id"), sa.column("category"), sa.column("value"),
                     sa.column("label"), sa.column("sort_order"), sa.column("metadata_json", sa.JSON()),
                     sa.column("is_active"), sa.column("created_at", sa.DateTime()), sa.column("updated_at", sa.DateTime()))
    connection = op.get_bind()
    for index, (value, label) in enumerate([("walk_in", "Walk-in"), ("appointment", "Appointment")]):
        if not connection.scalar(sa.select(table.c.id).where(table.c.category == "patient_source", table.c.value == value)):
            connection.execute(table.insert().values(id=str(uuid4()), category="patient_source", value=value,
                label=label, sort_order=index, metadata_json={}, is_active=True,
                created_at=datetime.utcnow(), updated_at=datetime.utcnow()))


def downgrade():
    with op.batch_alter_table("queue_tokens") as batch:
        batch.drop_constraint("uq_registration_serial", type_="unique")
        for name in ["serial_number", "age", "unit", "mri_area", "contrast", "film", "report", "patient_source"]:
            batch.drop_column(name)
    op.drop_table("registration_counters")
