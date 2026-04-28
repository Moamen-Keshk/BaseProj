"""revenue optimization layer

Revision ID: 3b1c7f2a9d4e
Revises: 61bc32442aba
Create Date: 2026-04-28 18:05:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3b1c7f2a9d4e'
down_revision = '61bc32442aba'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('bookings', sa.Column('rate_plan_id', sa.Integer(), nullable=True))
    op.add_column(
        'bookings',
        sa.Column('pricing_channel_code', sa.String(length=32), nullable=True, server_default='direct'),
    )
    op.create_index(op.f('ix_bookings_rate_plan_id'), 'bookings', ['rate_plan_id'], unique=False)
    op.create_foreign_key('fk_bookings_rate_plan_id', 'bookings', 'rate_plans', ['rate_plan_id'], ['id'])

    op.add_column('booking_rates', sa.Column('rate_plan_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_booking_rates_rate_plan_id'), 'booking_rates', ['rate_plan_id'], unique=False)
    op.create_foreign_key('fk_booking_rates_rate_plan_id', 'booking_rates', 'rate_plans', ['rate_plan_id'], ['id'])

    op.create_table(
        'daily_rate_plan_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('sellable_type_id', sa.Integer(), nullable=False),
        sa.Column('rate_plan_id', sa.Integer(), nullable=False),
        sa.Column('stay_date', sa.Date(), nullable=False),
        sa.Column('channel_code', sa.String(length=32), nullable=False, server_default='base'),
        sa.Column('base_amount', sa.Float(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('min_los', sa.Integer(), nullable=True),
        sa.Column('max_los', sa.Integer(), nullable=True),
        sa.Column('closed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('closed_to_arrival', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('closed_to_departure', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('source_type', sa.String(length=32), nullable=False, server_default='rate_plan'),
        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('explanation_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.ForeignKeyConstraint(['rate_plan_id'], ['rate_plans.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'property_id', 'sellable_type_id', 'rate_plan_id', 'stay_date', 'channel_code',
            name='uq_daily_rate_plan_state',
        ),
    )
    op.create_index(op.f('ix_daily_rate_plan_state_property_id'), 'daily_rate_plan_state', ['property_id'], unique=False)
    op.create_index(op.f('ix_daily_rate_plan_state_sellable_type_id'), 'daily_rate_plan_state', ['sellable_type_id'], unique=False)
    op.create_index(op.f('ix_daily_rate_plan_state_rate_plan_id'), 'daily_rate_plan_state', ['rate_plan_id'], unique=False)
    op.create_index(op.f('ix_daily_rate_plan_state_stay_date'), 'daily_rate_plan_state', ['stay_date'], unique=False)
    op.create_index(op.f('ix_daily_rate_plan_state_channel_code'), 'daily_rate_plan_state', ['channel_code'], unique=False)

    op.create_table(
        'revenue_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('sellable_type_id', sa.Integer(), nullable=False),
        sa.Column('channel_code', sa.String(length=32), nullable=False, server_default='base'),
        sa.Column('min_rate', sa.Float(), nullable=True),
        sa.Column('max_rate', sa.Float(), nullable=True),
        sa.Column('high_occupancy_threshold', sa.Float(), nullable=False, server_default='0.75'),
        sa.Column('low_occupancy_threshold', sa.Float(), nullable=False, server_default='0.35'),
        sa.Column('high_occupancy_uplift_pct', sa.Float(), nullable=False, server_default='12'),
        sa.Column('low_occupancy_discount_pct', sa.Float(), nullable=False, server_default='8'),
        sa.Column('short_lead_time_days', sa.Integer(), nullable=False, server_default='7'),
        sa.Column('short_lead_uplift_pct', sa.Float(), nullable=False, server_default='10'),
        sa.Column('long_lead_time_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('long_lead_discount_pct', sa.Float(), nullable=False, server_default='5'),
        sa.Column('pickup_window_days', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('pickup_uplift_pct', sa.Float(), nullable=False, server_default='6'),
        sa.Column('channel_adjustment_pct', sa.Float(), nullable=False, server_default='0'),
        sa.Column('auto_apply_min_confidence', sa.Float(), nullable=False, server_default='0.85'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('property_id', 'sellable_type_id', 'channel_code', name='uq_revenue_policy'),
    )
    op.create_index(op.f('ix_revenue_policies_property_id'), 'revenue_policies', ['property_id'], unique=False)
    op.create_index(op.f('ix_revenue_policies_sellable_type_id'), 'revenue_policies', ['sellable_type_id'], unique=False)
    op.create_index(op.f('ix_revenue_policies_channel_code'), 'revenue_policies', ['channel_code'], unique=False)

    op.create_table(
        'market_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('sellable_type_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('uplift_pct', sa.Float(), nullable=False, server_default='0'),
        sa.Column('flat_delta', sa.Float(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_market_events_property_id'), 'market_events', ['property_id'], unique=False)
    op.create_index(op.f('ix_market_events_sellable_type_id'), 'market_events', ['sellable_type_id'], unique=False)

    op.create_table(
        'revenue_recommendations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('sellable_type_id', sa.Integer(), nullable=False),
        sa.Column('rate_plan_id', sa.Integer(), nullable=False),
        sa.Column('stay_date', sa.Date(), nullable=False),
        sa.Column('channel_code', sa.String(length=32), nullable=False, server_default='base'),
        sa.Column('baseline_amount', sa.Float(), nullable=False),
        sa.Column('recommended_amount', sa.Float(), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('reason_codes_json', sa.JSON(), nullable=True),
        sa.Column('explanation_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.ForeignKeyConstraint(['rate_plan_id'], ['rate_plans.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'property_id', 'sellable_type_id', 'rate_plan_id', 'stay_date', 'channel_code',
            name='uq_revenue_recommendation',
        ),
    )
    op.create_index(op.f('ix_revenue_recommendations_property_id'), 'revenue_recommendations', ['property_id'], unique=False)
    op.create_index(op.f('ix_revenue_recommendations_sellable_type_id'), 'revenue_recommendations', ['sellable_type_id'], unique=False)
    op.create_index(op.f('ix_revenue_recommendations_rate_plan_id'), 'revenue_recommendations', ['rate_plan_id'], unique=False)
    op.create_index(op.f('ix_revenue_recommendations_stay_date'), 'revenue_recommendations', ['stay_date'], unique=False)
    op.create_index(op.f('ix_revenue_recommendations_channel_code'), 'revenue_recommendations', ['channel_code'], unique=False)
    op.create_index(op.f('ix_revenue_recommendations_status'), 'revenue_recommendations', ['status'], unique=False)

    op.create_table(
        'revenue_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('sellable_type_id', sa.Integer(), nullable=False),
        sa.Column('rate_plan_id', sa.Integer(), nullable=False),
        sa.Column('stay_date', sa.Date(), nullable=False),
        sa.Column('channel_code', sa.String(length=32), nullable=False, server_default='base'),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('previous_amount', sa.Float(), nullable=True),
        sa.Column('new_amount', sa.Float(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.ForeignKeyConstraint(['rate_plan_id'], ['rate_plans.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_revenue_audit_logs_property_id'), 'revenue_audit_logs', ['property_id'], unique=False)
    op.create_index(op.f('ix_revenue_audit_logs_sellable_type_id'), 'revenue_audit_logs', ['sellable_type_id'], unique=False)
    op.create_index(op.f('ix_revenue_audit_logs_rate_plan_id'), 'revenue_audit_logs', ['rate_plan_id'], unique=False)
    op.create_index(op.f('ix_revenue_audit_logs_stay_date'), 'revenue_audit_logs', ['stay_date'], unique=False)
    op.create_index(op.f('ix_revenue_audit_logs_channel_code'), 'revenue_audit_logs', ['channel_code'], unique=False)
    op.create_index(op.f('ix_revenue_audit_logs_created_at'), 'revenue_audit_logs', ['created_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_revenue_audit_logs_created_at'), table_name='revenue_audit_logs')
    op.drop_index(op.f('ix_revenue_audit_logs_channel_code'), table_name='revenue_audit_logs')
    op.drop_index(op.f('ix_revenue_audit_logs_stay_date'), table_name='revenue_audit_logs')
    op.drop_index(op.f('ix_revenue_audit_logs_rate_plan_id'), table_name='revenue_audit_logs')
    op.drop_index(op.f('ix_revenue_audit_logs_sellable_type_id'), table_name='revenue_audit_logs')
    op.drop_index(op.f('ix_revenue_audit_logs_property_id'), table_name='revenue_audit_logs')
    op.drop_table('revenue_audit_logs')

    op.drop_index(op.f('ix_revenue_recommendations_status'), table_name='revenue_recommendations')
    op.drop_index(op.f('ix_revenue_recommendations_channel_code'), table_name='revenue_recommendations')
    op.drop_index(op.f('ix_revenue_recommendations_stay_date'), table_name='revenue_recommendations')
    op.drop_index(op.f('ix_revenue_recommendations_rate_plan_id'), table_name='revenue_recommendations')
    op.drop_index(op.f('ix_revenue_recommendations_sellable_type_id'), table_name='revenue_recommendations')
    op.drop_index(op.f('ix_revenue_recommendations_property_id'), table_name='revenue_recommendations')
    op.drop_table('revenue_recommendations')

    op.drop_index(op.f('ix_market_events_sellable_type_id'), table_name='market_events')
    op.drop_index(op.f('ix_market_events_property_id'), table_name='market_events')
    op.drop_table('market_events')

    op.drop_index(op.f('ix_revenue_policies_channel_code'), table_name='revenue_policies')
    op.drop_index(op.f('ix_revenue_policies_sellable_type_id'), table_name='revenue_policies')
    op.drop_index(op.f('ix_revenue_policies_property_id'), table_name='revenue_policies')
    op.drop_table('revenue_policies')

    op.drop_index(op.f('ix_daily_rate_plan_state_channel_code'), table_name='daily_rate_plan_state')
    op.drop_index(op.f('ix_daily_rate_plan_state_stay_date'), table_name='daily_rate_plan_state')
    op.drop_index(op.f('ix_daily_rate_plan_state_rate_plan_id'), table_name='daily_rate_plan_state')
    op.drop_index(op.f('ix_daily_rate_plan_state_sellable_type_id'), table_name='daily_rate_plan_state')
    op.drop_index(op.f('ix_daily_rate_plan_state_property_id'), table_name='daily_rate_plan_state')
    op.drop_table('daily_rate_plan_state')

    op.drop_constraint('fk_booking_rates_rate_plan_id', 'booking_rates', type_='foreignkey')
    op.drop_index(op.f('ix_booking_rates_rate_plan_id'), table_name='booking_rates')
    op.drop_column('booking_rates', 'rate_plan_id')

    op.drop_constraint('fk_bookings_rate_plan_id', 'bookings', type_='foreignkey')
    op.drop_index(op.f('ix_bookings_rate_plan_id'), table_name='bookings')
    op.drop_column('bookings', 'pricing_channel_code')
    op.drop_column('bookings', 'rate_plan_id')
