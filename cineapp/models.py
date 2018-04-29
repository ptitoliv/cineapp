# -*- coding: utf-8 -*-
from cineapp import app,db
from sqlalchemy import desc,text, DefaultClause, orm
import flask.ext.whooshalchemy as whooshalchemy
from whoosh.analysis import CharsetFilter, NgramWordAnalyzer
from whoosh import fields
from whoosh.support.charset import accent_map
from whoosh.support.charset import default_charset, charset_table_to_dict
from cineapp.types import JSONEncodedDict
from sqlalchemy import tuple_

class User(db.Model):

	__tablename__ = "users"
	__table_args__ = {'mysql_charset': 'utf8', 'mysql_collate': 'utf8_general_ci'}

	id = db.Column(db.Integer, primary_key=True)
	nickname = db.Column(db.String(64), index=True, unique=True)
	password = db.Column(db.String(255))
	email = db.Column(db.String(120), index=True, unique=True)
	avatar = db.Column(db.String(255), unique=True)
	notifications = db.Column(JSONEncodedDict(255), nullable=False)
	graph_color = db.Column(db.String(6))
	added_movies = db.relationship('Movie', backref='added_by', lazy='dynamic')
	posted_messages = db.relationship('ChatMessage', backref='posted_by', lazy='dynamic')
	subscriptions = db.relationship('PushNotification',backref='user',lazy="dynamic")

	@property
	def is_authenticated(self):
		return True

	@property
	def is_active(self):
		return True

	@property
	def is_anonymous(self):
		return False

	@property
	def is_guest(self):
		return self.guest

	def get_id(self):
		try:
			return unicode(self.id) # Python 2
		except NameError:
			return str(self.id) # Python 3

	def __repr__(self):
		return '<User %r>' % (self.nickname)

    	def __init__(self,guest=False):
		self.notifications={ "notif_own_activity" : None,
			"notif_movie_add" : None,
			"notif_mark_add": None,
			"notif_homework_add": None,
			"notif_comment_add": None,
			"notif_favorite_update": None,
			"notif_chat_message": None,
			"notif_slack": None
		}
		if guest == True:
			self.nickname = "Guest"
			self.id = -1

		self.guest=guest


	@orm.reconstructor
    	def init_on_load(self):
        	self.guest=False

	def serialize(self):
		return {
			"id": self.id,
			"nickname": self.nickname,
			"password": self.password,
			"email": self.email,
			"avatar": self.avatar,
			"notifications": self.notifications,
			"graph_color": self.graph_color
		}

class Type(db.Model):
	
	__tablename__ = "types"
	__table_args__ = {'mysql_charset': 'utf8', 'mysql_collate': 'utf8_general_ci'}
	
	id = db.Column(db.String(5),primary_key=True)
	type = db.Column(db.String(20), unique=True)
	movies = db.relationship('Movie', backref='type_object', lazy='dynamic')

class Origin(db.Model):
	
	__tablename__ = "origins"
	__table_args__ = {'mysql_charset': 'utf8', 'mysql_collate': 'utf8_general_ci'}
	
	id = db.Column(db.String(5),primary_key=True)
	origin = db.Column(db.String(50), unique=True)
	movies = db.relationship('Movie', backref='origin_object', lazy='dynamic')

class Movie(db.Model):

	__tablename__ = "movies"
	__table_args__ = {'mysql_charset': 'utf8', 'mysql_collate': 'utf8_general_ci'}

	# Settings for FTS (WooshAlchemy)
	__searchable__ = [ 'name', 'director', 'original_name' ]
	charmap = charset_table_to_dict(default_charset)
	__analyzer__ = NgramWordAnalyzer(3) | CharsetFilter(charmap)

	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(100),index=True)
	original_name = db.Column(db.String(100),index=True)
	release_date = db.Column(db.Date, index=True)
	type = db.Column(db.String(5), db.ForeignKey('types.id'),index=True)
	url = db.Column(db.String(100), index=True)
	origin = db.Column(db.String(5), db.ForeignKey('origins.id'), index=True)
	director = db.Column(db.String(50), index=True)
	duration = db.Column(db.Integer())
	overview = db.Column(db.String(2000))
	tmvdb_id = db.Column(db.Integer, unique=True)
	poster_path = db.Column(db.String(255))
	added_when = db.Column(db.DateTime())
	added_by_user = db.Column(db.Integer, db.ForeignKey('users.id'))

	def __repr__(self):
		return '<Movie %r>' % (self.name)

	def next(self):
		"""
			Return the next item into the database
			Let's consider alphabetical order
		"""
		return db.session.query(Movie).filter(tuple_(Movie.name,Movie.release_date) > tuple_(self.name,self.release_date)).order_by(Movie.name,Movie.release_date).first()

	def prev(self):
		"""
			Return the previous item into the database
			Let's consider alphabetical order
		"""
		return db.session.query(Movie).filter(tuple_(Movie.name,Movie.release_date) < tuple_(self.name,self.release_date)).order_by(desc(Movie.name),desc(Movie.release_date)).first()

class Mark(db.Model):
	
	__tablename__ = "marks"
	__table_args__ = {'mysql_charset': 'utf8', 'mysql_collate': 'utf8_general_ci'}

	user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
	movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'), primary_key=True)
	seen_when = db.Column(db.Date)
	seen_where = db.Column(db.String(4))
	mark = db.Column(db.Float)
	updated_when = db.Column(db.DateTime())
	comment = db.Column(db.String(2000))
	homework_when = db.Column(db.DateTime)
	# Server_default allow to put the column with DEFAULT VALUE to NULL which is mandatory if we want the foreign key to be added
	# If the value is not NULL, the default value is O so the foreign constraint is violated
	homework_who = db.Column(db.Integer,db.ForeignKey('users.id'),nullable=True,server_default=text('NULL'))
	movie = db.relationship('Movie', backref='marked_by_users')
	user = db.relationship('User', backref='marked_movies',foreign_keys='Mark.user_id')
	homework_who_user = db.relationship('User', backref='given_homework',foreign_keys='Mark.homework_who')
	comments = db.relationship('MarkComment', backref='mark', order_by=desc("posted_when"))
	active_comments = db.relationship('MarkComment', order_by=desc("posted_when"), primaryjoin=("and_(MarkComment.mark_user_id==Mark.user_id, MarkComment.mark_movie_id==Mark.movie_id,MarkComment.deleted_when==None)"))

class ChatMessage(db.Model):
	__tablename__ = "chat_messages"
	__table_args__ = {'mysql_charset': 'utf8', 'mysql_collate': 'utf8_general_ci'}

	message_id = db.Column(db.Integer, primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
	posted_when = db.Column(db.DateTime())
	message = db.Column(db.String(1000))

class MarkComment(db.Model):
        __tablename__ = "mark_comment"
        __table_args__ = (db.ForeignKeyConstraint([ "mark_user_id", "mark_movie_id" ], [ "marks.user_id", "marks.movie_id" ]), {'mysql_charset': 'utf8', 'mysql_collate': 'utf8_general_ci'} )

        markcomment_id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
        mark_user_id = db.Column(db.Integer)
        mark_movie_id = db.Column(db.Integer)
        posted_when = db.Column(db.DateTime())
        deleted_when = db.Column(db.DateTime())
        message = db.Column(db.String(1000))
	user = db.relationship("User", backref="comments")
	old_message = None

	def serialize(self):
		return {
			"markcomment_id": self.markcomment_id,
			"user_id": self.user_id,
			"mark_user_id": self.mark_user_id,
			"mark_movie_id": self.mark_movie_id,
			"posted_when": self.posted_when,
			"message": self.message
		}

class FavoriteMovie(db.Model):
	__tablename__ = "favorite_movies"
	__table_args__ = {'mysql_charset': 'utf8', 'mysql_collate': 'utf8_general_ci'}

	movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'), primary_key=True)
	user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
	movie = db.relationship('Movie', backref='favorite_users',lazy="joined")
	user = db.relationship('User', backref='favorite_movies',foreign_keys='FavoriteMovie.user_id',lazy="joined")
	star_type = db.Column(db.String(100),db.ForeignKey('favorite_types.star_type'))
        added_when = db.Column(db.DateTime())
        deleted_when = db.Column(db.DateTime())

	def serialize(self):
		return {
			"movie_id": self.movie_id,
			"user_id": self.user_id,
			"star_type": self.star_type,
			"added_when": self.added_when,
			"deleted_when": self.deleted_when
		}

class FavoriteType(db.Model):
	__tablename__ = "favorite_types"
	__table_args__ = {'mysql_charset': 'utf8', 'mysql_collate': 'utf8_general_ci'}

	star_type = db.Column(db.String(20), primary_key=True)
	star_weight = db.Column(db.Integer)
	star_message = db.Column(db.String(100))
	movies = db.relationship('FavoriteMovie',backref='star_type_obj',lazy="dynamic")

	def serialize(self):
		return {
			"star_type": self.star_type,
			"star_message": self.star_message,
		}

class PushNotification(db.Model):
	__tablename__ = "push_notifications"
	__table_args__ = {'mysql_charset': 'utf8', 'mysql_collate': 'utf8_general_ci'}

	endpoint_id = db.Column(db.String(255), primary_key=True)
	auth_token = db.Column(db.String(128))
	public_key = db.Column(db.String(128))
	session_id = db.Column(db.String(255),index=True,unique=True)
	user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

	def serialize(self):
		return {
			"endpoint": self.endpoint_id,
			"keys":
				{ 'p256dh': self.public_key,
				  'auth': self.auth_token
				}
			}

# Enable FTS indexation
whooshalchemy.whoosh_index(app, Movie)
