"""empty message

Revision ID: 174c2484b0b8
Revises: e17dba181dd0
Create Date: 2024-12-02 03:40:06.176618

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '174c2484b0b8'
down_revision = 'e17dba181dd0'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('check_out_year', sa.Integer(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_column('check_out_year')

    # ### end Alembic commands ###
