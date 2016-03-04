"""empty message

Revision ID: 06472926c257
Revises: d19230f9ce03
Create Date: 2016-02-27 13:45:34.801279

"""

# revision identifiers, used by Alembic.
revision = '06472926c257'
down_revision = 'd19230f9ce03'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('movies', sa.Column('poster_path', sa.String(length=255), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('movies', 'poster_path')
    ### end Alembic commands ###
