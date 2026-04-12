"""add guest message delivery fields

Revision ID: 9a6b7c1d2e3f
Revises: f1a2b3c4d5e6
Create Date: 2026-04-12 19:40:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a6b7c1d2e3f'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('guest_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subject', sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column('delivery_status', sa.String(length=32), nullable=False, server_default='sent')
        )
        batch_op.add_column(sa.Column('delivery_error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('external_message_id', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('sent_by_user_id', sa.String(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_guest_messages_sent_by_user_id'), ['sent_by_user_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_guest_messages_sent_by_user_id',
            'users',
            ['sent_by_user_id'],
            ['uid'],
        )

    op.execute(
        """
        UPDATE guest_messages
        SET delivery_status = CASE
            WHEN direction = 'inbound' THEN 'received'
            ELSE 'sent'
        END
        """
    )


def downgrade():
    with op.batch_alter_table('guest_messages', schema=None) as batch_op:
        batch_op.drop_constraint('fk_guest_messages_sent_by_user_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_guest_messages_sent_by_user_id'))
        batch_op.drop_column('sent_by_user_id')
        batch_op.drop_column('external_message_id')
        batch_op.drop_column('delivery_error')
        batch_op.drop_column('delivery_status')
        batch_op.drop_column('subject')
