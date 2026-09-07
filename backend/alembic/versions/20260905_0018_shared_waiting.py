"""Allow registrations to wait without an assigned radiographer or consultation room."""
import sqlalchemy as sa

from alembic import op

revision = '20260905_0018'
down_revision = '20260905_0017'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('queue_tokens') as batch:
        batch.alter_column('doctor_id', existing_type=sa.String(60), nullable=True)


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text('SELECT COUNT(*) FROM queue_tokens WHERE doctor_id IS NULL')):
        raise RuntimeError('Unassigned registrations exist; retain the shared waiting schema until they are assigned.')
    with op.batch_alter_table('queue_tokens') as batch:
        batch.alter_column('doctor_id', existing_type=sa.String(60), nullable=False)
