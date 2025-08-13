"""add free_searches_remaining to user (safe backfill)

Revision ID: 299771da5831
Revises: DOWN_REV   # <-- replace with the actual previous revision id
Create Date: 2025-08-12
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '299771da5831'
down_revision = 'DOWN_REV'  # <-- replace this with the real one
branch_labels = None
depends_on = None


def upgrade():
    # 1) Add the column as nullable with a server default so existing rows get a value
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'free_searches_remaining',
                sa.Integer(),
                nullable=True,
                server_default=sa.text('0')  # choose a different default if you prefer
            )
        )

    # 2) Explicitly backfill any NULLs (belt-and-suspenders)
    op.execute('UPDATE "user" SET free_searches_remaining = 0 WHERE free_searches_remaining IS NULL')

    # 3) Enforce NOT NULL and drop the default so new writes must set a value (or your app does)
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column(
            'free_searches_remaining',
            existing_type=sa.Integer(),
            nullable=False,
            server_default=None
        )


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('free_searches_remaining')
