"""add rate plan pricing engine fields

Revision ID: b7c4f1d92e11
Revises: a91f3e8d4b2c
Create Date: 2026-04-12 12:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c4f1d92e11'
down_revision = 'a91f3e8d4b2c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('rate_plans', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pricing_type', sa.String(length=32), nullable=False, server_default='standard'))
        batch_op.add_column(sa.Column('parent_rate_plan_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('derived_adjustment_type', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('derived_adjustment_value', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('included_occupancy', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('single_occupancy_rate', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('extra_adult_rate', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('extra_child_rate', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('min_los', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('max_los', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('closed', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('closed_to_arrival', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('closed_to_departure', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('meal_plan_code', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('cancellation_policy', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('los_pricing', sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            'fk_rate_plans_parent_rate_plan_id',
            'rate_plans',
            ['parent_rate_plan_id'],
            ['id'],
        )


def downgrade():
    with op.batch_alter_table('rate_plans', schema=None) as batch_op:
        batch_op.drop_constraint('fk_rate_plans_parent_rate_plan_id', type_='foreignkey')
        batch_op.drop_column('los_pricing')
        batch_op.drop_column('cancellation_policy')
        batch_op.drop_column('meal_plan_code')
        batch_op.drop_column('closed_to_departure')
        batch_op.drop_column('closed_to_arrival')
        batch_op.drop_column('closed')
        batch_op.drop_column('max_los')
        batch_op.drop_column('min_los')
        batch_op.drop_column('extra_child_rate')
        batch_op.drop_column('extra_adult_rate')
        batch_op.drop_column('single_occupancy_rate')
        batch_op.drop_column('included_occupancy')
        batch_op.drop_column('derived_adjustment_value')
        batch_op.drop_column('derived_adjustment_type')
        batch_op.drop_column('parent_rate_plan_id')
        batch_op.drop_column('pricing_type')
