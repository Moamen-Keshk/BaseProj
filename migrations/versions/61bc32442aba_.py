"""empty message

Revision ID: 61bc32442aba
Revises:
Create Date: 2026-04-18 18:10:58.630455

"""


# revision identifiers, used by Alembic.
revision = '61bc32442aba'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # These indexes back active foreign keys on MySQL, so dropping them breaks
    # existing schemas. Keep this revision as a no-op.
    pass


def downgrade():
    pass
