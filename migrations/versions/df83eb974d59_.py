"""Improve production status display

Revision ID: df83eb974d59
Revises: edec70effd74
Create Date: 2021-06-19 11:07:39.026760

"""

# revision identifiers, used by Alembic.
revision = 'df83eb974d59'
down_revision = 'edec70effd74'

from alembic import op
import sqlalchemy as sa
import cineapp.migration_types



def upgrade():

    op.create_table('production_status',
    sa.Column('production_status', sa.String(length=30), nullable=False),
    sa.Column('translated_status', sa.String(length=50), nullable=True),
    sa.Column('style', sa.String(length=30), nullable=True),
    sa.PrimaryKeyConstraint('production_status'),
    mysql_charset='utf8',
    mysql_collate='utf8_general_ci'
    )
    op.add_column('tvshows', sa.Column('production_status', sa.String(length=30), nullable=True))
    op.create_foreign_key(None, 'tvshows', 'production_status', ['production_status'], ['production_status'])

    # Insert default data
    conn = op.get_bind()
    conn.execute("INSERT INTO production_status (`production_status`, `translated_status`, `style`) VALUES('Canceled','Annulée','danger')")
    conn.execute("INSERT INTO production_status (`production_status`, `translated_status`, `style`) VALUES('Ended','Terminée','success')")
    conn.execute("INSERT INTO production_status (`production_status`, `translated_status`, `style`) VALUES('In Production','En Production','warning')")
    conn.execute("INSERT INTO production_status (`production_status`, `translated_status`, `style`) VALUES('Pilot','Pilote','info')")
    conn.execute("INSERT INTO production_status (`production_status`, `translated_status`, `style`) VALUES('Returning Series','En cours / Renouvellée','info')")
    # ### end Alembic commands ###


def downgrade():

    op.drop_constraint('tvshows_ibfk_2', 'tvshows', type_='foreignkey')
    op.drop_column('tvshows', 'production_status')
    op.drop_table('production_status')
    # ### end Alembic commands ###
