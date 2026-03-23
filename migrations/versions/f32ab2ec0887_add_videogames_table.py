"""Add videogames table

Revision ID: f32ab2ec0887
Revises: 2b951c30abd6
Create Date: 2026-03-07

"""

# revision identifiers, used by Alembic.
revision = 'f32ab2ec0887'
down_revision = '2b951c30abd6'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # Add external_id column to shows table (replaces tmvdb_id in movies/tvshows and igdb_id in videogames)
    op.add_column('shows', sa.Column('external_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_shows_external_id'), 'shows', ['external_id'], unique=False)

    # Add overview_translated flag
    op.add_column('shows', sa.Column('overview_translated', sa.Boolean(), nullable=True, server_default='0'))

    # Migrate tmvdb_id data from movies and tvshows into shows.external_id
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE shows s INNER JOIN movies m ON s.id = m.id SET s.external_id = m.tmvdb_id"))
    conn.execute(sa.text("UPDATE shows s INNER JOIN tvshows t ON s.id = t.id SET s.external_id = t.tmvdb_id"))

    # Drop tmvdb_id from movies and tvshows
    op.drop_constraint('tmvdb_id', 'movies', type_='unique')
    op.drop_column('movies', 'tmvdb_id')
    op.drop_constraint('tmvdb_id', 'tvshows', type_='unique')
    op.drop_column('tvshows', 'tmvdb_id')

    # Create videogames table (without igdb_id, uses shows.external_id)
    op.create_table('videogames',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('platforms', sa.String(length=500), nullable=True),
    sa.Column('publisher', sa.String(length=500), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['shows.id'], name='videogames_ibfk_1'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8',
    mysql_collate='utf8_general_ci'
    )

    # Add videogame type entry
    op.execute("INSERT INTO types (id, type) VALUES ('VG', 'Jeu vidéo')")


def downgrade():
    op.execute("DELETE FROM types WHERE id = 'VG'")
    op.drop_table('videogames')

    # Re-add tmvdb_id to movies and tvshows
    op.add_column('movies', sa.Column('tmvdb_id', sa.Integer(), nullable=True))
    op.create_unique_constraint('tmvdb_id', 'movies', ['tmvdb_id'])
    op.add_column('tvshows', sa.Column('tmvdb_id', sa.Integer(), nullable=True))
    op.create_unique_constraint('tmvdb_id', 'tvshows', ['tmvdb_id'])

    # Migrate external_id back to movies and tvshows
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE movies m INNER JOIN shows s ON m.id = s.id SET m.tmvdb_id = s.external_id"))
    conn.execute(sa.text("UPDATE tvshows t INNER JOIN shows s ON t.id = s.id SET t.tmvdb_id = s.external_id"))

    # Drop external_id and overview_translated from shows
    op.drop_index(op.f('ix_shows_external_id'), table_name='shows')
    op.drop_column('shows', 'external_id')
    op.drop_column('shows', 'overview_translated')
