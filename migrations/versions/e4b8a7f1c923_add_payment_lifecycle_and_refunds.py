"""add payment lifecycle and refunds

Revision ID: e4b8a7f1c923
Revises: c6f1a2d9e411
Create Date: 2026-04-12 18:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4b8a7f1c923'
down_revision = 'c6f1a2d9e411'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('transaction_type', sa.String(length=32), nullable=True, server_default='payment'))
        batch_op.add_column(sa.Column('parent_transaction_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('external_channel', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('processor_reference', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('processor_status', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('effective_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('settlement_date', sa.Date(), nullable=True))
        batch_op.create_index(batch_op.f('ix_transactions_parent_transaction_id'), ['parent_transaction_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_transactions_parent_transaction_id',
            'transactions',
            ['parent_transaction_id'],
            ['id'],
        )

    op.execute(
        """
        UPDATE transactions
        SET
            transaction_type = COALESCE(transaction_type, 'payment'),
            processor_status = COALESCE(processor_status, status),
            effective_date = COALESCE(effective_date, DATE(created_at)),
            settlement_date = CASE
                WHEN settlement_date IS NOT NULL THEN settlement_date
                WHEN status IN ('succeeded', 'captured', 'settled') THEN DATE(created_at)
                ELSE settlement_date
            END
        """
    )


def downgrade():
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transactions_parent_transaction_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_transactions_parent_transaction_id'))
        batch_op.drop_column('settlement_date')
        batch_op.drop_column('effective_date')
        batch_op.drop_column('processor_status')
        batch_op.drop_column('processor_reference')
        batch_op.drop_column('external_channel')
        batch_op.drop_column('parent_transaction_id')
        batch_op.drop_column('transaction_type')
