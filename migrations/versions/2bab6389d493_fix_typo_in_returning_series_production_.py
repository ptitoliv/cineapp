"""Fix typo in Returning Series production status label

Revision ID: 2bab6389d493
Revises: d4e5f6a7b8c9
Create Date: 2026-07-08 21:48:13.635943

"""

# revision identifiers, used by Alembic.
revision = '2bab6389d493'
down_revision = 'd4e5f6a7b8c9'

from alembic import op
import sqlalchemy as sa
import cineapp.migration_types



def upgrade():
    # Fix the French label typo seeded in df83eb974d59: "Renouvellée" -> "Renouvelée"
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE production_status SET `translated_status`='En cours / Renouvelée' WHERE `production_status`='Returning Series'"))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE production_status SET `translated_status`='En cours / Renouvellée' WHERE `production_status`='Returning Series'"))
