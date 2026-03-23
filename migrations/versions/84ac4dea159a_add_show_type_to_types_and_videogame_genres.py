"""Add show_type column to types table and insert videogame genres

Revision ID: 84ac4dea159a
Revises: f32ab2ec0887
Create Date: 2026-03-07

"""

# revision identifiers, used by Alembic.
revision = '84ac4dea159a'
down_revision = 'f32ab2ec0887'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # Widen the type column to support longer genre names
    op.alter_column('types', 'type',
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=True)

    # Drop unique constraint on type name to allow duplicates across show types
    op.drop_constraint('type', 'types', type_='unique')

    # Add show_type column to filter genres by show type (movie, tvshow, videogame)
    op.add_column('types', sa.Column('show_type', sa.String(length=50), nullable=True))

    # Tag existing types as shared between movies and tvshows
    op.execute("UPDATE types SET show_type = 'movie' WHERE show_type IS NULL AND id != 'VG'")

    # Remove the VG placeholder type (replaced by actual genres below)
    op.execute("DELETE FROM types WHERE id = 'VG'")

    # Insert videogame genres in French
    videogame_genres = [
        ("PC", "Point & click", "videogame"),
        ("CBT", "Combat", "videogame"),
        ("FPS", "Tir / FPS", "videogame"),
        ("MUS", "Musique / Rythme", "videogame"),
        ("PLT", "Plateforme", "videogame"),
        ("PUZ", "Réflexion / Puzzle", "videogame"),
        ("CRS", "Course", "videogame"),
        ("STR", "Stratégie temps réel", "videogame"),
        ("RPG", "Jeu de rôle (RPG)", "videogame"),
        ("SIM", "Simulation", "videogame"),
        ("SPT", "Sport", "videogame"),
        ("STA", "Stratégie", "videogame"),
        ("TBS", "Stratégie au tour par tour", "videogame"),
        ("TAC", "Tactique", "videogame"),
        ("HNS", "Hack & slash / Beat'em up", "videogame"),
        ("QUZ", "Quiz / Trivia", "videogame"),
        ("FLP", "Flipper", "videogame"),
        ("AVT", "Aventure", "videogame"),
        ("IND", "Indépendant", "videogame"),
        ("ARC", "Arcade", "videogame"),
        ("VN", "Visual Novel", "videogame"),
        ("JCP", "Jeu de cartes / plateau", "videogame"),
        ("MOB", "MOBA", "videogame"),
        ("INC", "Inclassable", "videogame"),
    ]

    for genre_id, genre_name, show_type in videogame_genres:
        op.execute(
            "INSERT INTO types (id, type, show_type) VALUES ('%s', '%s', '%s')"
            % (genre_id, genre_name.replace("'", "\\'"), show_type)
        )


def downgrade():
    # Remove videogame genres
    op.execute("DELETE FROM types WHERE show_type = 'videogame'")

    # Re-insert the VG placeholder
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('VG', 'Jeu vidéo', 'videogame')")

    # Remove show_type tagging
    op.execute("UPDATE types SET show_type = NULL")

    # Drop show_type column
    op.drop_column('types', 'show_type')

    # Revert type column width
    op.alter_column('types', 'type',
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=True)
