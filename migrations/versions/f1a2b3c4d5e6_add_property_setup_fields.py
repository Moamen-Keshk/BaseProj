"""add property setup fields

Revision ID: f1a2b3c4d5e6
Revises: e4b8a7f1c923
Create Date: 2026-04-12 20:15:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e4b8a7f1c923'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('properties', schema=None) as batch_op:
        batch_op.add_column(sa.Column('timezone', sa.String(length=64), nullable=True, server_default='UTC'))
        batch_op.add_column(sa.Column('currency', sa.String(length=3), nullable=True, server_default='USD'))
        batch_op.add_column(sa.Column('tax_rate', sa.Float(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('default_check_in_time', sa.String(length=5), nullable=True, server_default='15:00'))
        batch_op.add_column(sa.Column('default_check_out_time', sa.String(length=5), nullable=True, server_default='11:00'))

    op.execute(
        """
        UPDATE properties
        SET
            timezone = COALESCE(timezone, 'UTC'),
            currency = COALESCE(currency, 'USD'),
            tax_rate = COALESCE(tax_rate, 0),
            default_check_in_time = COALESCE(default_check_in_time, '15:00'),
            default_check_out_time = COALESCE(default_check_out_time, '11:00')
        """
    )


def downgrade():
    with op.batch_alter_table('properties', schema=None) as batch_op:
        batch_op.drop_column('default_check_out_time')
        batch_op.drop_column('default_check_in_time')
        batch_op.drop_column('tax_rate')
        batch_op.drop_column('currency')
        batch_op.drop_column('timezone')
