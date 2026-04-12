"""add room_online rate plan tracking

Revision ID: a91f3e8d4b2c
Revises: d2d7c6b3a12f
Create Date: 2026-04-12 11:40:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a91f3e8d4b2c'
down_revision = 'd2d7c6b3a12f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('room_online', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rate_plan_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_room_online_rate_plan_id'), ['rate_plan_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_room_online_rate_plan_id',
            'rate_plans',
            ['rate_plan_id'],
            ['id'],
        )


def downgrade():
    with op.batch_alter_table('room_online', schema=None) as batch_op:
        batch_op.drop_constraint('fk_room_online_rate_plan_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_room_online_rate_plan_id'))
        batch_op.drop_column('rate_plan_id')
