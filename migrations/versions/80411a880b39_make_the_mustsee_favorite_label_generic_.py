"""Make the mustsee favorite label generic (Incontournable)

Revision ID: 80411a880b39
Revises: 2bab6389d493
Create Date: 2026-07-18 02:15:46.155208

"""

# revision identifiers, used by Alembic.
revision = '80411a880b39'
down_revision = '2bab6389d493'

from alembic import op
import sqlalchemy as sa
import cineapp.migration_types



def upgrade():
    # The "mustsee" favorite label was movie/tvshow-centric ("A voir absolument").
    # Make it generic so it reads correctly for video games too (Incontournable).
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE favorite_types SET `star_message`='Incontournable' WHERE `star_type`='mustsee_star'"))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE favorite_types SET `star_message`='A voir absolument' WHERE `star_type`='mustsee_star'"))
