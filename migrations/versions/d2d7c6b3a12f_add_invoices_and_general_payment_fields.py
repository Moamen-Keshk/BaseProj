"""add invoices and general payment fields

Revision ID: d2d7c6b3a12f
Revises: 41b505f4e6c4
Create Date: 2026-04-12 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2d7c6b3a12f'
down_revision = '41b505f4e6c4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'invoices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_number', sa.String(length=32), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='open'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('issue_date', sa.Date(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('subtotal', sa.Float(), nullable=False, server_default='0'),
        sa.Column('tax_amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('total_amount', sa.Float(), nullable=False, server_default='0'),
        sa.Column('amount_paid', sa.Float(), nullable=False, server_default='0'),
        sa.Column('balance_due', sa.Float(), nullable=False, server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id']),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('booking_id'),
        sa.UniqueConstraint('invoice_number'),
    )

    op.create_table(
        'invoice_line_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('line_date', sa.Date(), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False, server_default='1'),
        sa.Column('unit_price', sa.Float(), nullable=False, server_default='0'),
        sa.Column('amount', sa.Float(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('invoice_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('payment_method', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('source', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('reference', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('recorded_by', sa.String(length=32), nullable=True))
        batch_op.alter_column('stripe_payment_intent_id', existing_type=sa.String(length=128), nullable=True)
        batch_op.create_foreign_key('fk_transactions_invoice_id', 'invoices', ['invoice_id'], ['id'])


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transactions_invoice_id', type_='foreignkey')
        batch_op.alter_column('stripe_payment_intent_id', existing_type=sa.String(length=128), nullable=False)
        batch_op.drop_column('recorded_by')
        batch_op.drop_column('notes')
        batch_op.drop_column('reference')
        batch_op.drop_column('source')
        batch_op.drop_column('payment_method')
        batch_op.drop_column('invoice_id')

    op.drop_table('invoice_line_items')
    op.drop_table('invoices')
