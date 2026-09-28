"""Designation updates: SNK rename, remove spouse/child/parent/soldier, ensure other, default mandatory fields."""
from datetime import datetime
from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = '20260928_0029'
down_revision = '20260928_0028'
branch_labels = None
depends_on = None

DEFAULT_REQUIRED = ['patient_name', 'rank', 'service_number', 'beneficiary_type', 'patient_source', 'family_relationship']
ALL_FIELDS = [
    'patient_name', 'patient_phone', 'patient_source', 'service_number', 'age', 'unit',
    'mri_area', 'contrast', 'film', 'report', 'rank', 'priority', 'beneficiary_type',
    'entitlement', 'service_status', 'family_relationship',
]


def upgrade():
    connection = op.get_bind()
    options = sa.table(
        'lookup_options',
        sa.column('id', sa.String),
        sa.column('category', sa.String),
        sa.column('value', sa.String),
        sa.column('label', sa.String),
        sa.column('sort_order', sa.Integer),
        sa.column('is_active', sa.Boolean),
        sa.column('metadata_json', sa.JSON),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    tokens = sa.table(
        'queue_tokens',
        sa.column('id', sa.String),
        sa.column('rank', sa.String),
    )
    settings = sa.table(
        'app_settings',
        sa.column('key', sa.String),
        sa.column('description', sa.String),
        sa.column('value', sa.JSON),
    )

    # 1. Update shoinik / sainik -> snk / SNK
    connection.execute(
        options.update()
        .where(options.c.category == 'rank_relationship', options.c.value == 'shoinik')
        .values(value='snk', label='SNK')
    )
    connection.execute(
        options.update()
        .where(
            options.c.category == 'rank_relationship',
            sa.or_(
                options.c.value == 'snk',
                options.c.label.in_(['Shoinik / Sainik', 'Shoinik', 'Sainik'])
            )
        )
        .values(label='SNK')
    )
    connection.execute(
        tokens.update()
        .where(tokens.c.rank == 'shoinik')
        .values(rank='snk')
    )

    # 2. Remove spouse, child, parent, soldier from rank_relationship
    connection.execute(
        options.delete().where(
            options.c.category == 'rank_relationship',
            options.c.value.in_(['spouse', 'child', 'parent', 'soldier'])
        )
    )

    # 3. Ensure 'other' exists in rank_relationship
    has_other = connection.execute(
        sa.select(options.c.id).where(
            options.c.category == 'rank_relationship',
            options.c.value == 'other'
        )
    ).scalar_one_or_none()
    now = datetime.utcnow()
    if not has_other:
        connection.execute(
            options.insert().values(
                id=str(uuid4()),
                category='rank_relationship',
                value='other',
                label='Other',
                sort_order=99,
                is_active=True,
                metadata_json={'report_group': 'or'},
                created_at=now,
                updated_at=now,
            )
        )

    # 4. Make designation (rank), service_number, beneficiary_type, patient_source mandatory by default
    setting_row = connection.execute(
        sa.select(settings.c.value).where(settings.c.key == 'registration_fields')
    ).scalar_one_or_none()

    if setting_row is not None:
        val = dict(setting_row)
        req = list(val.get('required') or ['patient_name'])
        for f in ['rank', 'service_number', 'beneficiary_type', 'patient_source']:
            if f not in req:
                req.append(f)
        val['required'] = req

        enabled = list(val.get('enabled') or ALL_FIELDS)
        for f in ['rank', 'service_number', 'beneficiary_type', 'patient_source']:
            if f not in enabled:
                enabled.append(f)
        val['enabled'] = enabled

        connection.execute(
            settings.update()
            .where(settings.c.key == 'registration_fields')
            .values(value=val)
        )


def downgrade():
    pass
