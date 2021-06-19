"""Migration to hybrid mode (TVShows and movies)

Revision ID: edec70effd74
Revises: b037baf33cfa
Create Date: 2021-06-13 19:03:10.107347

"""

# revision identifiers, used by Alembic.
revision = 'edec70effd74'
down_revision = 'b037baf33cfa'

from alembic import op
import sqlalchemy as sa
import cineapp.migration_types
import json

from sqlalchemy.dialects import mysql

def upgrade():
   ### commands auto generated by Alembic - please adjust! ###

    # Create new show table
    op.create_table('shows',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=True),
    sa.Column('original_name', sa.String(length=100), nullable=True),
    sa.Column('release_date', sa.Date(), nullable=True),
    sa.Column('type', sa.String(length=5), nullable=True),
    sa.Column('url', sa.String(length=100), nullable=True),
    sa.Column('origin', sa.String(length=5), nullable=True),
    sa.Column('director', sa.String(length=500), nullable=True),
    sa.Column('overview', sa.String(length=2000), nullable=True),
    sa.Column('poster_path', sa.String(length=255), nullable=True),
    sa.Column('added_when', sa.DateTime(), nullable=True),
    sa.Column('added_by_user', sa.Integer(), nullable=True),
    sa.Column('show_type', sa.String(length=50), nullable=True),
    sa.ForeignKeyConstraint(['added_by_user'], ['users.id'], ),
    sa.ForeignKeyConstraint(['origin'], ['origins.id'], ),
    sa.ForeignKeyConstraint(['type'], ['types.id'], ),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8',
    mysql_collate='utf8_general_ci'
    )

    op.create_index(op.f('ix_shows_director'), 'shows', ['director'], unique=False)
    op.create_index(op.f('ix_shows_name'), 'shows', ['name'], unique=False)
    op.create_index(op.f('ix_shows_origin'), 'shows', ['origin'], unique=False)
    op.create_index(op.f('ix_shows_original_name'), 'shows', ['original_name'], unique=False)
    op.create_index(op.f('ix_shows_release_date'), 'shows', ['release_date'], unique=False)
    op.create_index(op.f('ix_shows_type'), 'shows', ['type'], unique=False)
    op.create_index(op.f('ix_shows_url'), 'shows', ['url'], unique=False)

    # Migrate data from movies table to show table
    conn=op.get_bind()
    conn.execute("INSERT INTO shows (`id`, `name`, `release_date`, `type`, `url`, `origin`, `director`, `overview`, `poster_path`, `added_when`, `added_by_user`, `original_name`, `show_type`) SELECT `id`, `name`, `release_date`, `type`, `url`, `origin`, `director`, `overview`, `poster_path`, `added_when`, `added_by_user`, `original_name`,\"movies\" FROM movies")

    op.create_table('tvshows',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nb_seasons', sa.Integer(), nullable=True),
    sa.Column('tmvdb_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['shows.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tmvdb_id'),
    mysql_charset='utf8',
    mysql_collate='utf8_general_ci'
    )

    # Rename movie_id column to show_id column and update associated foreign key
    op.drop_constraint('marks_ibfk_2', 'marks', type_='foreignkey')
    op.drop_index('movie_id', table_name='marks')
    op.alter_column('marks','movie_id', new_column_name='show_id', server_default=None, existing_server_default=None, nullable=False, existing_nullable=False, type_=None, existing_type=sa.Integer())
    op.create_foreign_key('marks_ibfk_2', 'marks', 'shows', ['show_id'], ['id'])
    #op.create_index(op.f('show_id'), 'marks', ['show_id'], unique=False)

    # Rename mark_movie_id column to mark_show_id and update associated foreign key
    op.drop_constraint('mark_comment_ibfk_1', 'mark_comment', type_='foreignkey')
    op.alter_column('mark_comment', 'mark_movie_id', new_column_name='mark_show_id', server_default=None, existing_server_default=None, nullable=False, existing_nullable=False, type_=None, existing_type=sa.Integer())
    op.create_foreign_key('mark_comment_ibfk_1', 'mark_comment', 'marks', ['mark_user_id', 'mark_show_id'], ['user_id', 'show_id'])

    # Rename table favorite_movies to favorite_shows
    op.drop_constraint('favorite_movies_ibfk_1', 'favorite_movies', type_='foreignkey')
    op.alter_column('favorite_movies', 'movie_id', new_column_name='show_id', server_default=None, existing_server_default=None, nullable=False, existing_nullable=False, type_=None, existing_type=sa.Integer())
    op.rename_table('favorite_movies','favorite_shows')
    op.create_foreign_key('favorite_shows_ibfk_1', 'favorite_shows', 'shows', ['show_id'], ['id'])

    # Create movies table
    op.create_table('movies_temp',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('duration', sa.Integer(), nullable=True),
    sa.Column('tmvdb_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['id'], ['shows.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tmvdb_id'),
    mysql_charset='utf8',
    mysql_collate='utf8_general_ci'
    )

    # Fill the movie table with correct data in order to handle correctly inheritance
    conn.execute("INSERT INTO movies_temp SELECT `id`, `duration`, `tmvdb_id` FROM movies")

    # Drop the old movie table and rename the temp table
    op.drop_table('movies')
    op.rename_table('movies_temp','movies')

    # Column upgrade
    op.alter_column('mark_comment', 'mark_show_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)

    # Update notification field with new notifications
    conn=op.get_bind()
    res = conn.execute("select id,notifications from users")
    results = res.fetchall()

    for cur_result in results:
        temp_id=cur_result[0]
        temp_dict=json.loads(cur_result[1])
        temp_notif_value=temp_dict["notif_movie_add"]
        del temp_dict["notif_movie_add"]
        temp_dict["notif_show_add"]=temp_notif_value
        final_dict=json.dumps(temp_dict)

        # Update the notification field into the database
        conn.execute("UPDATE users SET notifications='%s' WHERE id=%s" % (json.dumps(temp_dict), temp_id))
    # ### end Alembic commands ###

def downgrade():

    # ### commands auto generated by Alembic - please adjust! ###

    # Create movie table with a temporary name because the inherited movies table still exists
    op.create_table('movies_temp',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=True),
    sa.Column('original_name', sa.String(length=100), nullable=True),
    sa.Column('release_date', sa.Date(), nullable=True),
    sa.Column('type', sa.String(length=5), nullable=True),
    sa.Column('url', sa.String(length=100), nullable=True),
    sa.Column('origin', sa.String(length=5), nullable=True),
    sa.Column('director', sa.String(length=200), nullable=True),
    sa.Column('duration', sa.Integer(), nullable=True),
    sa.Column('overview', sa.String(length=2000), nullable=True),
    sa.Column('tmvdb_id', sa.Integer(), nullable=True),
    sa.Column('poster_path', sa.String(length=255), nullable=True),
    sa.Column('added_when', sa.DateTime(), nullable=True),
    sa.Column('added_by_user', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['added_by_user'], ['users.id'], ),
    sa.ForeignKeyConstraint(['origin'], ['origins.id'], ),
    sa.ForeignKeyConstraint(['type'], ['types.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tmvdb_id'),
    mysql_charset='utf8',
    mysql_collate='utf8_general_ci'
    )

    # Upgrade columns
    op.alter_column('mark_comment', 'mark_show_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)

    # Migrate data from show and movies table
    conn=op.get_bind()
    conn.execute("INSERT INTO movies_temp (`id`, `name`, `release_date`, `type`, `url`, `origin`, `director`, `overview`, `poster_path`, `added_when`, `added_by_user`, `original_name`) SELECT `id`, `name`, `release_date`, `type`, `url`, `origin`, `director`, `overview`, `poster_path`, `added_when`, `added_by_user`, `original_name` FROM shows")
    conn.execute("UPDATE movies_temp mo SET mo.duration=(SELECT m.duration FROM movies m WHERE m.id=mo.id)")

    # Rename the movies_temp table with the definitive name
    # But remove constraints linked to that table before
    op.drop_constraint('marks_ibfk_2', 'marks', type_='foreignkey')
    op.drop_constraint('favorite_shows_ibfk_1', 'favorite_shows', type_='foreignkey')
    op.drop_table('movies')
    op.rename_table('movies_temp','movies')

    # Rename show_id column to movie_id column and update associated foreign key
    op.alter_column('marks','show_id', new_column_name='movie_id', server_default=None, existing_server_default=None, nullable=False, existing_nullable=False, type_=None, existing_type=sa.Integer())
    op.create_foreign_key('marks_ibfk_2', 'marks', 'movies', ['movie_id'], ['id'])

    # Rename mark_show_id column to mark_movie_id and update associated foreign key
    op.drop_constraint('mark_comment_ibfk_1', 'mark_comment', type_='foreignkey')
    op.alter_column('mark_comment', 'mark_show_id', new_column_name='mark_movie_id', server_default=None, existing_server_default=None, nullable=False, existing_nullable=False, type_=None, existing_type=sa.Integer())
    op.create_foreign_key('mark_comment_ibfk_1', 'mark_comment', 'marks', ['mark_user_id', 'mark_movie_id'], ['user_id', 'movie_id'])

    # Rename table favorite_shows to favorite_movies
    op.alter_column('favorite_shows', 'show_id', new_column_name='movie_id', server_default=None, existing_server_default=None, nullable=False, existing_nullable=False, type_=None, existing_type=sa.Integer())
    op.rename_table('favorite_shows','favorite_movies')
    op.create_foreign_key('favorite_movies_ibfk_1', 'favorite_movies', 'movies', ['movie_id'], ['id'])

    # Delete obsolete tables
    op.drop_table('tvshows')
    op.drop_table('shows')

    # Update notification field with new notifications
    conn=op.get_bind()
    res = conn.execute("select id,notifications from users")
    results = res.fetchall()

    for cur_result in results:
        temp_id=cur_result[0]
        temp_dict=json.loads(cur_result[1])
        temp_notif_value=temp_dict["notif_show_add"]
        del temp_dict["notif_show_add"]
        temp_dict["notif_movie_add"]=temp_notif_value
        final_dict=json.dumps(temp_dict)

        # Update the notification field into the database
        conn.execute("UPDATE users SET notifications='%s' WHERE id=%s" % (json.dumps(temp_dict), temp_id))

    # Create missing index
    op.create_index(op.f('movie_id'), 'marks', ['movie_id'], unique=False)

    # ### end Alembic commands ###
