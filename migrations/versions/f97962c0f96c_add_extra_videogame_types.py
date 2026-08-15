"""Add extra videogame types

Revision ID: f97962c0f96c
Revises: 9a145ba5b160
Create Date: 2026-08-15 23:33:47.277130

"""

# revision identifiers, used by Alembic.
revision = 'f97962c0f96c'
down_revision = '9a145ba5b160'

from alembic import op
import sqlalchemy as sa


def upgrade():
    # New genres requested on top of the 84ac4dea159a base set
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('TPS', 'Third Person Shooter (TPS)', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('ACT', 'Action', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('BTA', 'Beat Them All', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('RGL', 'Rogue Like', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('INF', 'Infiltration', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('SLK', 'Souls-Like', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('GOD', 'God Game', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('ARPG', 'Action RPG', 'videogame')")
    op.execute("INSERT INTO types (id, type, show_type) VALUES ('PRTY', 'Party Game', 'videogame')")


def downgrade():
    # Remove only the genres added by this revision
    op.execute("DELETE FROM types WHERE id = 'TPS' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'ACT' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'BTA' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'RGL' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'INF' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'SLK' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'GOD' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'ARPG' AND show_type = 'videogame'")
    op.execute("DELETE FROM types WHERE id = 'PRTY' AND show_type = 'videogame'")
