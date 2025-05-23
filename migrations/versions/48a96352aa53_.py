"""empty message

Revision ID: 48a96352aa53
Revises: 
Create Date: 2025-04-23 15:36:59.704703

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '48a96352aa53'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('blocks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('block_date', sa.Date(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('start_day', sa.Integer(), nullable=True),
    sa.Column('start_month', sa.Integer(), nullable=True),
    sa.Column('start_year', sa.Integer(), nullable=True),
    sa.Column('end_day', sa.Integer(), nullable=True),
    sa.Column('end_month', sa.Integer(), nullable=True),
    sa.Column('end_year', sa.Integer(), nullable=True),
    sa.Column('number_of_days', sa.Integer(), nullable=True),
    sa.Column('property_id', sa.Integer(), nullable=False),
    sa.Column('room_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('blocks')
    # ### end Alembic commands ###
