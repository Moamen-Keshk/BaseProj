"""empty message

Revision ID: e17dba181dd0
Revises: 1427acb17d2a
Create Date: 2024-11-26 08:31:21.027074

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e17dba181dd0'
down_revision = '1427acb17d2a'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('bookings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('confirmation_number', sa.Integer(), nullable=True),
    sa.Column('first_name', sa.String(length=32), nullable=True),
    sa.Column('last_name', sa.String(length=32), nullable=True),
    sa.Column('number_of_adults', sa.Integer(), nullable=True),
    sa.Column('number_of_children', sa.Integer(), nullable=True),
    sa.Column('payment_status_id', sa.Integer(), nullable=True),
    sa.Column('status_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('special_request', sa.Text(), nullable=True),
    sa.Column('booking_date', sa.Date(), nullable=True),
    sa.Column('check_in', sa.Date(), nullable=True),
    sa.Column('check_out', sa.Date(), nullable=True),
    sa.Column('check_in_day', sa.Integer(), nullable=True),
    sa.Column('check_in_month', sa.Integer(), nullable=True),
    sa.Column('check_in_year', sa.Integer(), nullable=True),
    sa.Column('check_out_day', sa.Integer(), nullable=True),
    sa.Column('check_out_month', sa.Integer(), nullable=True),
    sa.Column('number_of_days', sa.Integer(), nullable=True),
    sa.Column('rate', sa.Double(), nullable=True),
    sa.Column('property_id', sa.Integer(), nullable=True),
    sa.Column('room_id', sa.Integer(), nullable=True),
    sa.Column('creator_id', sa.String(length=32), nullable=True),
    sa.ForeignKeyConstraint(['payment_status_id'], ['payment_status.id'], ),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ),
    sa.ForeignKeyConstraint(['status_id'], ['booking_status.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('confirmation_number')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('bookings')
    # ### end Alembic commands ###
