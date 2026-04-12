"""add notification metadata fields

Revision ID: b4f8c2d1e9a0
Revises: 9a6b7c1d2e3f
Create Date: 2026-04-12 20:25:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4f8c2d1e9a0'
down_revision = '9a6b7c1d2e3f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notification_type', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('property_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('entity_type', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('entity_id', sa.String(length=64), nullable=True))
        batch_op.alter_column('routing', existing_type=sa.String(length=32), type_=sa.String(length=64))
        batch_op.create_index(batch_op.f('ix_notifications_notification_type'), ['notification_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_property_id'), ['property_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_notifications_property_id',
            'properties',
            ['property_id'],
            ['id'],
        )


def downgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('fk_notifications_property_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_notifications_property_id'))
        batch_op.drop_index(batch_op.f('ix_notifications_notification_type'))
        batch_op.alter_column('routing', existing_type=sa.String(length=64), type_=sa.String(length=32))
        batch_op.drop_column('entity_id')
        batch_op.drop_column('entity_type')
        batch_op.drop_column('property_id')
        batch_op.drop_column('notification_type')
