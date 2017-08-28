"""Split subscription object in several columns

Revision ID: b75f7c7164ca
Revises: f66a92f1895f
Create Date: 2017-08-22 14:33:55.543213

"""

# revision identifiers, used by Alembic.
revision = 'b75f7c7164ca'
down_revision = 'f66a92f1895f'

from alembic import op
import sqlalchemy as sa
import cineapp.migration_types

from sqlalchemy.dialects import mysql

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('push_notifications', sa.Column('auth_token', sa.String(length=128), nullable=True))
    op.add_column('push_notifications', sa.Column('endpoint_id', sa.String(length=255), nullable=False))
    op.add_column('push_notifications', sa.Column('public_key', sa.String(length=128), nullable=True))
    op.drop_column('push_notifications', 'subscription_id')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('push_notifications', sa.Column('subscription_id', mysql.VARCHAR(length=255), nullable=False))
    op.drop_column('push_notifications', 'public_key')
    op.drop_column('push_notifications', 'endpoint_id')
    op.drop_column('push_notifications', 'auth_token')
    # ### end Alembic commands ###
