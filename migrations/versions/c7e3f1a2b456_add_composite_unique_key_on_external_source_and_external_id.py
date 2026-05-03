"""Add external_source column and composite unique key on (external_source, external_id)

Revision ID: c7e3f1a2b456
Revises: 84ac4dea159a
Create Date: 2026-03-29

"""

# revision identifiers, used by Alembic.
revision = 'c7e3f1a2b456'
down_revision = '84ac4dea159a'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('shows', sa.Column('external_source', sa.String(length=20), nullable=True))

    # Backfill: at this point in history all shows came from the TheMovieDB integration (cineapp/tmvdb.py)
    op.execute("UPDATE shows SET external_source = 'tmvdb' WHERE external_id IS NOT NULL")

    op.create_unique_constraint('uq_shows_external', 'shows', ['external_source', 'external_id'])


def downgrade():
    op.drop_constraint('uq_shows_external', 'shows', type_='unique')
    op.drop_column('shows', 'external_source')
