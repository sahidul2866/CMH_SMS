"""Use rank for both the patient and a family patient's sponsor.

Stored report classification snapshots are not recalculated. Downgrade restores
family sponsor ranks from rank; it cannot recreate previously conflicting values.
"""
from alembic import op
import sqlalchemy as sa

revision = '20260926_0026'
down_revision = '20260926_0025'
branch_labels = None
depends_on = None


def family_values(connection):
    options = sa.table('lookup_options', sa.column('category', sa.String), sa.column('value', sa.String), sa.column('metadata_json', sa.JSON))
    values = {'family'}
    for row in connection.execute(sa.select(options).where(options.c.category == 'beneficiary_type')).mappings():
        if (row['metadata_json'] or {}).get('report_code') == 'family':
            values.add(row['value'])
    return values


def upgrade():
    connection = op.get_bind()
    with op.batch_alter_table('queue_tokens') as batch:
        batch.alter_column('rank', existing_type=sa.String(60), type_=sa.String(100), existing_nullable=True)
    tokens = sa.table('queue_tokens', sa.column('rank', sa.String), sa.column('sponsor_rank', sa.String), sa.column('beneficiary_type', sa.String))
    connection.execute(tokens.update().where(
        tokens.c.sponsor_rank.is_not(None), sa.func.trim(tokens.c.sponsor_rank) != '',
        sa.or_(tokens.c.beneficiary_type.in_(family_values(connection)), tokens.c.rank.is_(None), sa.func.trim(tokens.c.rank) == '')
    ).values(rank=tokens.c.sponsor_rank))
    settings = sa.table('app_settings', sa.column('key', sa.String), sa.column('value', sa.JSON))
    value = connection.execute(sa.select(settings.c.value).where(settings.c.key == 'registration_fields')).scalar_one_or_none()
    if value is not None:
        value = dict(value)
        for key in ('required', 'enabled'):
            if key in value:
                value[key] = list(dict.fromkeys('rank' if field == 'sponsor_rank' else field for field in value[key]))
        connection.execute(settings.update().where(settings.c.key == 'registration_fields').values(value=value))
    with op.batch_alter_table('queue_tokens') as batch:
        batch.drop_column('sponsor_rank')


def downgrade():
    op.add_column('queue_tokens', sa.Column('sponsor_rank', sa.String(100), nullable=True))
    connection = op.get_bind()
    tokens = sa.table('queue_tokens', sa.column('rank', sa.String), sa.column('sponsor_rank', sa.String), sa.column('beneficiary_type', sa.String))
    connection.execute(tokens.update().where(tokens.c.beneficiary_type.in_(family_values(connection))).values(sponsor_rank=tokens.c.rank))
    # Retain rank's wider size and unified field policy to avoid truncating data
    # or guessing which pre-migration settings the administrator had selected.
