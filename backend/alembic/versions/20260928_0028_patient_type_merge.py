"""Merge entitlement options into beneficiary_type lookup options."""
from datetime import datetime
from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = '20260928_0028'
down_revision = '20260928_0027'
branch_labels = None
depends_on = None


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
        sa.column('beneficiary_type', sa.String),
        sa.column('entitlement', sa.String),
    )

    existing_b = {
        row['value']
        for row in connection.execute(
            sa.select(options.c.value).where(options.c.category == 'beneficiary_type')
        ).mappings()
    }
    now = datetime.utcnow()
    if 're' not in existing_b:
        connection.execute(
            options.insert().values(
                id=str(uuid4()),
                category='beneficiary_type',
                value='re',
                label='RE',
                sort_order=2,
                is_active=True,
                metadata_json={'report_code': 're'},
                created_at=now,
                updated_at=now,
            )
        )
    if 'cne' not in existing_b:
        connection.execute(
            options.insert().values(
                id=str(uuid4()),
                category='beneficiary_type',
                value='cne',
                label='CNE',
                sort_order=3,
                is_active=True,
                metadata_json={'report_code': 'cne'},
                created_at=now,
                updated_at=now,
            )
        )
    else:
        connection.execute(
            options.update()
            .where(options.c.category == 'beneficiary_type', options.c.value == 'cne')
            .values(label='CNE')
        )

    # Backfill historical tokens where entitlement was re or cne but beneficiary_type was unset
    connection.execute(
        tokens.update()
        .where(tokens.c.entitlement == 're', sa.or_(tokens.c.beneficiary_type.is_(None), tokens.c.beneficiary_type == ''))
        .values(beneficiary_type='re')
    )
    connection.execute(
        tokens.update()
        .where(tokens.c.entitlement == 'cne', sa.or_(tokens.c.beneficiary_type.is_(None), tokens.c.beneficiary_type == ''))
        .values(beneficiary_type='cne')
    )


def downgrade():
    pass
