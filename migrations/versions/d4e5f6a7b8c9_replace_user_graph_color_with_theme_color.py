"""Replace User.graph_color with User.theme_color

The BS3-era graph_color (VARCHAR(6), hex without leading `#`) is replaced
by theme_color (VARCHAR(7) with leading `#`, NOT NULL DEFAULT `#b08c00`).
theme_color is the per-user accent colour used across the editorial UI
(avatars, score badges, graph series, activity-feed avatars). Historical
BS3 hex values are not preserved — the editorial palette is the source
of truth now.

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-05-23

"""

# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'a1b2c3d4e5f6'

from alembic import op
import sqlalchemy as sa


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('theme_color', sa.String(length=7),
                                      server_default='#b08c00', nullable=False))
        batch_op.drop_column('graph_color')


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('graph_color', sa.String(length=6), nullable=True))
        batch_op.drop_column('theme_color')
