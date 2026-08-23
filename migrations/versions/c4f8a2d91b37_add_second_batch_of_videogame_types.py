"""Add second batch of videogame types

Revision ID: c4f8a2d91b37
Revises: f97962c0f96c
Create Date: 2026-08-19 01:20:00.000000

"""

# revision identifiers, used by Alembic.
revision = 'c4f8a2d91b37'
down_revision = 'f97962c0f96c'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # PLT keeps its id and rows but now means 2D platformers only (3D gets
    # its own genre below)
    op.execute("UPDATE types SET type = 'Plateforme 2D' WHERE id = 'PLT' AND show_type = 'videogame'")

    # Second batch of genres on top of the f97962c0f96c set
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('P3D', 'Plateforme 3D', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('BEU', 'Beat \\'em up', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('MTV', 'Metroidvania', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('SHMUP', 'Shoot \\'em up / Shooter', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('ENQ', 'Enquête', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('OPW', 'Open World', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('SRV', 'Survival', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('SVH', 'Survival Horror', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('IMS', 'Immersive Sim', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('SDV', 'Simulation de vie', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('GST', 'Gestion', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('WLK', 'Walking Simulator', 'videogame')")


def downgrade():
    # Remove only the genres added by this revision
    op.execute("DELETE FROM types WHERE id = 'P3D' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'BEU' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'MTV' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'SHMUP' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'ENQ' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'OPW' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'SRV' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'SVH' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'IMS' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'SDV' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'GST' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'WLK' AND show_type = 'videogame'")

    # Restore the generic platformer label
    op.execute("UPDATE types SET type = 'Plateforme' WHERE id = 'PLT' AND show_type = 'videogame'")
