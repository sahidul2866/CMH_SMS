"""Add military designations and patient origin options without replacing custom values."""
from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "20260905_0017"
down_revision = "20260905_0016"
branch_labels = None
depends_on = None

OPTIONS = {
    "patient_source": [("opd", "OPD"), ("ipd", "IPD / Ward"), ("emergency", "Emergency"), ("referral", "Referral")],
    "rank_relationship": [("brigadier_general", "Brigadier General"), ("colonel", "Colonel"),
        ("lieutenant_colonel", "Lieutenant Colonel"), ("major", "Major"), ("captain", "Captain"),
        ("lieutenant", "Lieutenant"), ("warrant_officer", "Warrant Officer"), ("sergeant", "Sergeant"),
        ("corporal", "Corporal"), ("shoinik", "Shoinik / Sainik"), ("vip", "VIP")],
}


def upgrade():
    table = sa.table("lookup_options", sa.column("id"), sa.column("category"), sa.column("value"),
                     sa.column("label"), sa.column("sort_order"), sa.column("metadata_json", sa.JSON()),
                     sa.column("is_active"), sa.column("created_at", sa.DateTime()), sa.column("updated_at", sa.DateTime()))
    connection = op.get_bind()
    for category, choices in OPTIONS.items():
        for index, (value, label) in enumerate(choices):
            if not connection.scalar(sa.select(table.c.id).where(table.c.category == category, table.c.value == value)):
                metadata = {"priority": "vip"} if category == "rank_relationship" and value in {"brigadier_general", "vip"} else {}
                connection.execute(table.insert().values(id=str(uuid4()), category=category, value=value,
                    label=label, sort_order=index, metadata_json=metadata, is_active=True,
                    created_at=datetime.utcnow(), updated_at=datetime.utcnow()))


def downgrade():
    # Lookup records can be referenced by registrations; retain them on downgrade.
    pass
