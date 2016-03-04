"""empty message

Revision ID: 0f7a85013413
Revises: addc6e40cee6
Create Date: 2016-02-20 17:48:35.452457

"""

# revision identifiers, used by Alembic.
revision = '0f7a85013413'
down_revision = 'addc6e40cee6'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('marks', 'movie_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('marks', 'movie_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
    ### end Alembic commands ###
