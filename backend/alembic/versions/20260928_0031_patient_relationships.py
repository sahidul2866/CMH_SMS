"""Install patient-type-specific relationships, retaining historical values."""
from datetime import datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = '20260928_0031'
down_revision = '20260928_0030'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    options = sa.table('lookup_options', sa.column('id', sa.String), sa.column('category', sa.String),
        sa.column('value', sa.String), sa.column('label', sa.String), sa.column('sort_order', sa.Integer),
        sa.column('is_active', sa.Boolean), sa.column('metadata_json', sa.JSON),
        sa.column('created_at', sa.DateTime), sa.column('updated_at', sa.DateTime))
    relationships = ('daughter', 'son', 'wife', 'husband', 'mother', 'father', 'mother_in_law', 'father_in_law')
    now = datetime.utcnow()
    connection.execute(options.update().where(options.c.category == 'family_relationship',
        options.c.value.not_in(relationships)).values(is_active=False, updated_at=now))
    for order, value in enumerate(relationships):
        existing = connection.execute(sa.select(options).where(options.c.category == 'family_relationship',
            options.c.value == value)).mappings().first()
        values = dict(label=value.replace('_', ' ').upper(), sort_order=order, is_active=True,
                      metadata_json={**(existing['metadata_json'] or {} if existing else {}), 'report_code': value},
                      updated_at=now)
        if existing:
            connection.execute(options.update().where(options.c.id == existing['id']).values(**values))
        else:
            connection.execute(options.insert().values(id=str(uuid4()), category='family_relationship',
                               value=value, created_at=now, **values))
    # Do not guess whether historical spouse/child/parent records meant wife, son, etc.
    # Saved summary mappings and historical category snapshots remain intact.


def downgrade():
    pass
