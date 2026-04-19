"""Add regions table

Revision ID: a1b2c3d4e5f6
Revises: c7e3f1a2b456
Create Date: 2026-04-17

"""

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'c7e3f1a2b456'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('regions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('region_name', sa.String(length=50), nullable=False),
        sa.Column('region_translated_name', sa.String(length=50), nullable=False),
        sa.Column('flag_code', sa.String(length=10), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
        mysql_charset='utf8',
        mysql_collate='utf8_general_ci'
    )

    # Populate with IGDB regions and lipis flag-icons codes
    # priority: 1=highest, NULL=no priority
    op.execute("INSERT INTO regions (id, region_name, region_translated_name, flag_code, priority) VALUES (1, 'europe', 'Europe', 'eu', 4)")
    op.execute("INSERT INTO regions (id, region_name, region_translated_name, flag_code, priority) VALUES (2, 'north_america', 'Amérique du Nord', 'us', 1)")
    op.execute("INSERT INTO regions (id, region_name, region_translated_name, flag_code, priority) VALUES (3, 'australia', 'Australie', 'au', 0)")
    op.execute("INSERT INTO regions (id, region_name, region_translated_name, flag_code, priority) VALUES (4, 'new_zealand', 'Nouvelle-Zélande', 'nz', 0)")
    op.execute("INSERT INTO regions (id, region_name, region_translated_name, flag_code, priority) VALUES (5, 'japan', 'Japon', 'jp', 2)")
    op.execute("INSERT INTO regions (id, region_name, region_translated_name, flag_code, priority) VALUES (6, 'china', 'Chine', 'cn', 0)")
    op.execute("INSERT INTO regions (id, region_name, region_translated_name, flag_code, priority) VALUES (7, 'asia', 'Asie', 'un', 0)")
    op.execute("INSERT INTO regions (id, region_name, region_translated_name, flag_code, priority) VALUES (8, 'worldwide', 'Monde', 'un', 3)")
    op.execute("INSERT INTO regions (id, region_name, region_translated_name, flag_code, priority) VALUES (9, 'korea', 'Corée', 'kr', 0)")
    op.execute("INSERT INTO regions (id, region_name, region_translated_name, flag_code, priority) VALUES (10, 'brazil', 'Brésil', 'br', 0)")

    # Add release_region_id FK column and release_platform column to videogames
    op.add_column('videogames', sa.Column('release_region_id', sa.Integer(), nullable=True))
    op.create_foreign_key('videogames_ibfk_2', 'videogames', 'regions', ['release_region_id'], ['id'])
    op.add_column('videogames', sa.Column('release_platform', sa.String(length=200), nullable=True))


def downgrade():
    op.drop_column('videogames', 'release_platform')
    op.drop_constraint('videogames_ibfk_2', 'videogames', type_='foreignkey')
    op.drop_column('videogames', 'release_region_id')
    op.drop_table('regions')
