"""add ready room cleaning status

Revision ID: c2f4b9d1e6aa
Revises: f87c8a140640
Create Date: 2026-04-06 18:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2f4b9d1e6aa'
down_revision = 'f87c8a140640'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    room_cleaning_status = sa.table(
        'room_cleaning_status',
        sa.column('id', sa.Integer),
        sa.column('code', sa.String),
        sa.column('name', sa.String),
        sa.column('color', sa.String),
    )

    existing_status_count = bind.execute(
        sa.select(sa.func.count()).select_from(room_cleaning_status)
    ).scalar()

    ready_exists = bind.execute(
        sa.select(room_cleaning_status.c.id).where(room_cleaning_status.c.name == 'Ready')
    ).first()

    if existing_status_count and not ready_exists:
        bind.execute(
            sa.insert(room_cleaning_status).values(
                code='READY',
                name='Ready',
                color='teal',
            )
        )


def downgrade():
    bind = op.get_bind()
    room_cleaning_status = sa.table(
        'room_cleaning_status',
        sa.column('name', sa.String),
    )

    bind.execute(
        sa.delete(room_cleaning_status).where(room_cleaning_status.c.name == 'Ready')
    )
