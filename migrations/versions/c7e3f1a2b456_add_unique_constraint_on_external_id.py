"""Add unique constraint on external_id

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
    # Drop the existing non-unique index
    op.drop_index(op.f('ix_shows_external_id'), table_name='shows')
    # Recreate it as unique
    op.create_index(op.f('ix_shows_external_id'), 'shows', ['external_id'], unique=True)


def downgrade():
    # Drop the unique index
    op.drop_index(op.f('ix_shows_external_id'), table_name='shows')
    # Recreate as non-unique
    op.create_index(op.f('ix_shows_external_id'), 'shows', ['external_id'], unique=False)
