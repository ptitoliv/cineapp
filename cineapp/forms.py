# -*- coding: utf-8 -*-

from flask.ext.wtf import Form
from flask.ext.wtf.html5 import SearchField
from wtforms import StringField, PasswordField, RadioField, SubmitField, HiddenField, SelectField, TextAreaField, BooleanField, DateField, FileField
from wtforms.ext.sqlalchemy.fields import QuerySelectField
from wtforms.validators import Required,DataRequired, EqualTo, Email, URL, ValidationError
from cineapp.models import Origin, Type, User
from cineapp.fields import CKTextAreaField, SearchButtonField
from datetime import datetime

def get_origins():
	return Origin.query.all()

def get_types():
	return Type.query.all()

def get_users():
	return User.query.all()

class LoginForm(Form):
	username = StringField('username', validators=[DataRequired()])
	password = PasswordField('password', validators=[DataRequired()])

class AddUserForm(Form):
	username = StringField('Nom Utilisateur', [DataRequired()])
	email = StringField('Adresse Email', [DataRequired(), Email(message="Adresse E-Mail Incorrecte")])
	password = PasswordField('Mot de passe',[DataRequired(), EqualTo('confirm',message='Les mots de passe ne correspondent pas')])
	confirm = PasswordField('Confirmation mot de passe')

class AddMovieForm(Form):
	name = StringField('Nom du Film', [DataRequired()])
	director = StringField('Realisateur', [DataRequired()])
	year = StringField('Annee de sortie', [DataRequired()])
	url = StringField('Fiche Allocine')
	origin = QuerySelectField(query_factory=get_origins, get_label='origin')
	type = QuerySelectField(query_factory=get_types,get_label='type')

class MarkMovieForm(Form):
	class Meta:
		locales = ('de_DE', 'de')

	mark = StringField('Note du Film', [DataRequired()])
	comment = CKTextAreaField('Commentaire du Film', [DataRequired()])
	seen_where = RadioField('Ou j\'ai vu le film', [Required(message="Date invalide")],choices=[('C', u'Cinema'), ('M', 'Maison')], default='M')
	seen_when = DateField('Vu le :', default=datetime.now,format="%d/%m/%Y")
	submit_mark = SubmitField('Noter')
	submit_mark_only = SubmitField('Noter uniquement')
	submit_mark_slack = SubmitField('Noter et publier')

	# The method name is important
	# A validate_XXX method will validate a field named XXX
	def validate_mark(form,field):
		try:
			float(field.data)
		except ValueError:
			raise ValidationError('Pas un chiffre')
		if float(field.data) < 0 or float(field.data) > 20:
			raise ValidationError('Note Incorrecte')

class SearchMovieForm(Form):
	search = StringField('Nom du film', [DataRequired()])
	submit_search = SearchButtonField(u"Chercher")

class SelectMovieForm(Form):
	movie = RadioField('Film',[Required(message="Veuillez sélectionner un film")],choices=[], coerce=int)
	submit_select = SubmitField(u'Sélectionner')

	# Specific constructer in order to pass a movie list
	def __init__(self,movies_list=[]):
	
		# Call the parent constructor
		super(SelectMovieForm, self).__init__()
		
		# Local variable
		choice_list=[]
		for cur_movie in movies_list:

			# Extract the year if we can
			if cur_movie.release_date != None and cur_movie.release_date != "":
				try:
					movie_year = datetime.strptime(cur_movie.release_date,"%Y-%m-%d").strftime("%Y")
				except ValueError:
					# If we are here that means the datetime module can't handle the date
					# Do it manually
					movie_year = cur_movie.release_date.split("-")[0] 
			else:
				movie_year = "Inconnu"

			choice_list.append((cur_movie.tmvdb_id, cur_movie.name + " ( " + movie_year + " - " + cur_movie.director + " )"))

		self.movie.choices = choice_list

class UpdateMovieForm(Form):
	movie_id = HiddenField()
	submit_update_movie = SubmitField(u'Mettre à jour le film')

class ConfirmMovieForm(Form):
	origin = QuerySelectField('Origine',query_factory=get_origins, get_label='origin')
	type = QuerySelectField('Type',query_factory=get_types,get_label='type')
	movie_id = HiddenField()
	submit_confirm = SubmitField("Ajouter le film")

class FilterForm(Form):
	origin = QuerySelectField('Origine',query_factory=get_origins, get_label='origin',allow_blank=True,blank_text=u'--Pas de filtre--')
	type = QuerySelectField('Type',query_factory=get_types,get_label='type',allow_blank=True,blank_text=u'--Pas de filtre--')
	where = QuerySelectField('Vu au cine par',query_factory=get_users,get_label='nickname',allow_blank=True,blank_text=u'--Pas de filtre--')
	favorite = QuerySelectField('Favori de',query_factory=get_users,get_label='nickname',allow_blank=True,blank_text=u'--Pas de filtre--')
	submit_filter = SubmitField("Filtrer")

class UserForm(Form):
	email = StringField('Adresse Email', [DataRequired('Champ Requis'), Email(message="Adresse E-Mail Incorrecte")])
	notif_own_activity = BooleanField()
	notif_movie_add = BooleanField()
	notif_mark_add = BooleanField()
	notif_homework_add = BooleanField()
	notif_comment_add = BooleanField()
	notif_favorite_update = BooleanField()
	notif_chat_message = BooleanField()
	notif_slack = BooleanField()
	submit_user = SubmitField("Sauver")
	upload_avatar = FileField("Image de profil")

	# Specific constructor in order to set notifications correctly
	def __init__(self,user=None,*args,**kwargs):
		
		# Call the parent constructor
		super(UserForm, self).__init__(obj=user,*args,**kwargs)

		# Fill the notifications field from using the dictionnary dict
		if user != None and user.notifications != None:

			if "notif_own_activity" in user.notifications and user.notifications["notif_own_activity"] != None:
				self.notif_own_activity.data=user.notifications["notif_own_activity"]

			if "notif_movie_add" in user.notifications and user.notifications["notif_movie_add"] != None:
				self.notif_movie_add.data=user.notifications["notif_movie_add"]

			if "notif_mark_add" in user.notifications and user.notifications["notif_mark_add"] != None:
				self.notif_mark_add.data=user.notifications["notif_mark_add"]

			if "notif_homework_add" in user.notifications and user.notifications["notif_homework_add"] != None:
				self.notif_homework_add.data=user.notifications["notif_homework_add"]

			if "notif_comment_add" in user.notifications and user.notifications["notif_comment_add"] != None:
				self.notif_comment_add.data=user.notifications["notif_comment_add"]

			if "notif_favorite_update" in user.notifications and user.notifications["notif_favorite_update"] != None:
				self.notif_favorite_update.data=user.notifications["notif_favorite_update"]

			if "notif_chat_message" in user.notifications and user.notifications["notif_chat_message"] != None:
				self.notif_chat_message.data=user.notifications["notif_chat_message"]

			if "notif_slack" in user.notifications and user.notifications["notif_slack"] != None:
				self.notif_slack.data=user.notifications["notif_slack"]

class PasswordForm(Form):
	password = PasswordField('Mot de passe',[DataRequired('Champ Requis'), EqualTo('confirm',message='Les mots de passe ne correspondent pas')])
	confirm = PasswordField('Confirmation mot de passe',[DataRequired('Champ Requis')])
	submit_user = SubmitField("Changer le mot de passe")

class HomeworkForm(Form):
	from_user_filter = QuerySelectField('De:',query_factory=get_users,get_label='nickname',allow_blank=True,blank_text=u'--Tous--')
	to_user_filter = QuerySelectField('A:',query_factory=get_users,get_label='nickname',allow_blank=True,blank_text=u'--Tous--')
	submit_homework = SubmitField('Filtrer')

class DashboardGraphForm(Form):
	user_list = QuerySelectField(query_factory=get_users,get_label='nickname')
