# -*- coding: utf-8 -*-

import urllib, hashlib, re, os, locale, json, copy, time
from datetime import datetime
from flask import render_template, flash, redirect, url_for, g, request, session
from flask.ext.login import login_user, logout_user, current_user, login_required
from flask.ext.wtf import Form
from wtforms.ext.sqlalchemy.orm import model_form
from wtforms.ext.sqlalchemy.fields import QuerySelectField
from cineapp import app, db, lm
from cineapp.forms import LoginForm, AddUserForm, AddMovieForm, MarkMovieForm, SearchMovieForm, SelectMovieForm, ConfirmMovieForm, FilterForm, UserForm, PasswordForm, HomeworkForm, UpdateMovieForm
from cineapp.models import User, Movie, Mark, Origin, Type
from cineapp.tvmdb import search_movies,get_movie,download_poster, search_page_number
from cineapp.emails import add_movie_notification, mark_movie_notification, add_homework_notification, update_movie_notification
from cineapp.utils import frange, get_activity_list, resize_avatar
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm.exc import FlushError
from sqlalchemy import desc, or_, and_, Table
from sqlalchemy.sql.expression import select, case, literal
from bcrypt import hashpw, gensalt
from werkzeug.utils import secure_filename

@app.route('/')
@app.route('/index')
def index():
	return redirect(url_for('login'))

@app.before_request
def before_request():
	# Store the current authenticated user into a global object
	# current_user set by flask
	# g set by flask
	g.user = current_user

	# Make the search form available in all templates (Including base.html)
	g.search_form = SearchMovieForm(prefix="search")

	# Make the graph list available in the whole app
	g.graph_list = app.config['GRAPH_LIST']

@app.route('/login', methods=['GET','POST'])
def login():

	# Let's check if we are authenticated => If yes redirect to the index page
	if g.user is not None and g.user.is_authenticated:
        	return redirect(url_for('show_dashboard'))

	# If we are here, we are not login. Build the form and try the login.
	form = LoginForm()
	if form.validate_on_submit():
		# Let's validate the user
		user=User.query.filter_by(nickname=form.username.data).first()
		if user is None:
			flash("Mauvais utilisateur !",'danger')
			return redirect(url_for('login'))
		else:
			if hashpw(form.password.data.encode('utf-8'), user.password.encode('utf-8')) != user.password:
				flash("Mot de passe incorrect !",'danger')
				return redirect(url_for('login'))
			# User authenticated => Let's login it
			login_user(user)
			return redirect(request.args.get('next') or url_for('index'))
		return redirect(url_for('index'))
	
	return render_template('login.html', title='Sign In', form=form)

@app.route('/logout')
def logout():
	logout_user()
	return redirect(url_for('index'))

@app.route('/movies/list')
@app.route('/movies/reset', endpoint="reset_list")
@app.route('/movies/filter', methods=[ 'GET', 'POST' ], endpoint="filter_form")
def list_movies():

	# Display the search form
	filter_form = FilterForm()

	# Fetch the query string or dict => We'll need it later
	session_query=session.get('query',None)
	
	# By default, don't clean the datatable state
	clear_table=False

	# If we catch the reset_list endpoint, well reset the list in initial state
	if request.endpoint == "reset_list":

		# Reset all the values in order to have the initial list
		session.pop('query',None)

		# Tell that we must reset the table on next load
		session['clear_table_on_next_reload']=True

		# And go back to the list
		return redirect(url_for("list_movies"))

	# We are in filter mode
	if g.search_form.submit_search.data == True:
		# We come from the form into the navbar
		if g.search_form.validate_on_submit():
			filter_string=g.search_form.search.data
			session['query']=filter_string

			session['search_type']="filter"
			
			# Reset the datatable to a fresh state
			clear_table=True

	elif filter_form.submit_filter.data == True:
		# We come from the filter form above the datatable
		# Build the filter request

		if filter_form.origin.data == None and filter_form.type.data == None and filter_form.where.data == None:
			# All filter are empty => Let's display the list
			session['search_type']="list"
		else:

			# Put the forms parameter into a session object in order to be handled by the datatable
			session['search_type']="filter_origin_type"
			filter_dict = {'origin' : None, 'type': None, 'seen_where' : None}

			if filter_form.origin.data != None:
				filter_dict['origin'] = filter_form.origin.data.id

			if filter_form.type.data != None:
				filter_dict['type'] = filter_form.type.data.id

			if filter_form.where.data != None:
				filter_dict['seenwhere'] = filter_form.where.data.id

			session['query']=filter_dict

		# Reset the datatable to a fresh state
		clear_table=True

	elif isinstance(session_query,dict):

		# We come from an homework link and we want to fill the form
		session['search_type']="filter_origin_type"
		
		# Rebuild the form setting default values stores into the session object
		# We need to check if the variable is not or none in order to avoid an exception
		if session_query['origin'] == None:
			origin = None
		else:
			origin=Origin.query.get(session_query['origin'])

		if session_query['type'] == None:
			type = None
		else:
			type=Type.query.get(session_query['type'])

		if session_query['seen_where'] == None:
			seen_where=None
		else:
			seen_where=User.query.get(session_query['seen_where'])

		# Recreate the form with the set default values
		filter_form=FilterForm(origin=origin,type=type,where=seen_where)

	else:
		# We are in list mode, check if we must clear the table after a reset
		session['search_type']="list"
		clear_table=session.pop('clear_table_on_next_reload',None)

	# Let's fetch all the users, I will need them
	users = User.query.all()
	return render_template('movies_list.html', users=users,filter_form=filter_form,clear_table=clear_table)

@app.route('/movies/json', methods=['GET','POST'])
@login_required
def update_datatable():

	# Local variables for handling the datatable
	args = json.loads(request.values.get("args"))
	columns = args.get("columns")
	start = args.get('start')
	length = args.get('length')
	draw = args.get('draw')
	order_by=args.get('order')
	order_column=columns[order_by[0]['column']]['data']
	order_dir=order_by[0]['dir']

	# Guess which is the sort column
	m=re.match('other_(.*)\.(.*)',order_column)

	# That first if is for the others column
	# Regex is matched
	if m != None:
		filter_user=m.group(2)
		if m.group(1) == "marks":
			filter_field = Mark.mark
		elif m.group(1) == "when":
			filter_field = Mark.seen_when
			
	# Filtering by logged user mark
	elif order_column == "my_mark":
		filter_user = g.user.id
		filter_field = Mark.mark

	# Filtering by logged user seen date
	elif order_column == "my_when":
		filter_user = g.user.id
		filter_field = Mark.seen_when
	else:
		filter_user = None

	# If we enter here, we are going to filter by user (my_* column or others_* column)	
	if filter_user != None:

		# Let's build the filtered requested following what has been posted in the filter form
		filter_fields=session.get('query')
		movies_query = Movie.query.outerjoin(Mark).filter_by(user_id=filter_user)

		# Check that we have a real list in order to avoid an exception	
		if isinstance(filter_fields,dict):
			if filter_fields['origin'] != None:
				movies_query = movies_query.filter(Movie.origin==filter_fields['origin'])

			if filter_fields['type'] != None:
				movies_query = movies_query.filter(Movie.type==filter_fields['type'])

			if filter_fields['seen_where'] != None:

				# We want to sort movies for a specific user keeping the seen_where filter enabled
				# So we want to see movies seen in theater (or not) by a user sorting these movies by marks of another user
				# Since we sort by marks, we don't want to see movies without a mark for that user
				# So we need that to build that specific subquery.

				# First let's fetch the movies seen by a user in theaters
				movies_seen_in_theater = Mark.query.filter(Mark.user_id==filter_fields['seen_where']).filter(Mark.seen_where=='C').all()
				array_movies_seen_in_theater = []

				# Then build a list of these movies
				for cur_movie_seen_in_theater in movies_seen_in_theater:
					array_movies_seen_in_theater.append(cur_movie_seen_in_theater.movie_id)
				
				# Finally let's build the filter that will be used later building the query
				movies_query = movies_query.filter(Mark.movie_id.in_(array_movies_seen_in_theater))

		# Sort my desc marks
		if order_dir == "desc":
			if session.get('search_type') == 'list': 
				movies = Movie.query.outerjoin(Mark).filter_by(user_id=filter_user).filter(filter_field != None).order_by(desc(filter_field)).slice(int(start),int(start) + int(length))
				count_movies=Movie.query.outerjoin(Mark).filter_by(user_id=filter_user).count()

			elif session.get('search_type') == 'filter_origin_type':
				movies = movies_query.filter(filter_field != None).order_by(desc(filter_field)).slice(int(start),int(start) + int(length))
				count_movies=movies_query.filter(Mark.mark != None).count()
					
			elif session.get('search_type') == 'filter':
				movies = Movie.query.outerjoin(Mark).whoosh_search(session.get('query')).filter_by(user_id=filter_user).filter(filter_field != None).order_by(desc(filter_field)).slice(int(start),int(start) + int(length))
				count_movies=Movie.query.outerjoin(Mark).whoosh_search(session.get('query')).filter_by(user_id=filter_user).filter(filter_field != None).count()

		# Sort by asc marks
		else:
			if session.get('search_type') == 'list': 
				movies = Movie.query.outerjoin(Mark).filter_by(user_id=filter_user).filter(filter_field != None).order_by(filter_field).slice(int(start),int(start) + int(length))
				count_movies=Movie.query.outerjoin(Mark).filter_by(user_id=filter_user).count()
			elif session.get('search_type') == 'filter_origin_type':
				movies = movies_query.filter(filter_field != None).order_by(filter_field).slice(int(start),int(start) + int(length))
				count_movies=movies_query.filter(filter_field != None).count()
			elif session.get('search_type') == 'filter':
				movies = Movie.query.outerjoin(Mark).whoosh_search(session.get('query')).filter_by(user_id=filter_user).filter(filter_field != None).order_by(filter_field).slice(int(start),int(start) + int(length))
				count_movies=Movie.query.outerjoin(Mark).whoosh_search(session.get('query')).filter_by(user_id=filter_user).count()
	else:
		# If we are are => No sort by user but only global sort or no sort
		if session.get('search_type') == 'list': 
			if order_column == "average":
				if order_dir == "desc":
					movies=db.session.query(Movie).join(Mark).group_by(Mark.movie_id).having(db.func.avg(Mark.mark!=None)).order_by(desc(db.func.avg(Mark.mark))).slice(int(start),int(start) + int(length))
				else:
					movies=db.session.query(Movie).join(Mark).group_by(Mark.movie_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).slice(int(start),int(start) + int(length))
				
				count_movies=db.session.query(Movie).join(Mark).group_by(Mark.movie_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).count()
			else:
				movies = Movie.query.order_by(order_column + " " + order_dir).slice(int(start),int(start) + int(length))
				count_movies=Movie.query.count()

		# Let's use the filter form
		elif session.get('search_type') == 'filter_origin_type':
			# Let's build the filtered requested following what has been posted in the filter form
			filter_fields=session.get('query')
			movies_query = Movie.query.join(Mark)

			if filter_fields['origin'] != None:
				movies_query = movies_query.filter(Movie.origin==filter_fields['origin'])

			if filter_fields['type'] != None:
				movies_query = movies_query.filter(Movie.type==filter_fields['type'])

			if filter_fields['seen_where'] !=None:
				movies_query = movies_query.filter_by(user_id=filter_fields['seen_where']).filter(Mark.seen_where=='C')

			# Build the request
			if order_column == "average":
				if order_dir == "desc":
					movies=movies_query.group_by(Mark.movie_id).having(db.func.avg(Mark.mark!=None)).order_by(desc(db.func.avg(Mark.mark))).slice(int(start),int(start) + int(length)).all()
				else:
					movies=movies_query.group_by(Mark.movie_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).slice(int(start),int(start) + int(length)).all()
			else:
				movies = movies_query.order_by(order_column + " " + order_dir).slice(int(start),int(start) + int(length))

			count_movies=movies_query.count()

		# Here, this is for the string search (Movie or director)
		elif session.get('search_type') == 'filter':
			if order_column == "average":
				if order_dir == "desc":
					movies=Movie.query.whoosh_search(session.get('query')).join(Mark).group_by(Mark.movie_id).having(db.func.avg(Mark.mark!=None)).order_by(desc(db.func.avg(Mark.mark))).slice(int(start),int(start) + int(length)).all()
				else:
					movies=Movie.query.whoosh_search(session.get('query')).join(Mark).group_by(Mark.movie_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).slice(int(start),int(start) + int(length)).all()
				count_movies=Movie.query.whoosh_search(session.get('query')).join(Mark).group_by(Mark.movie_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).count()
			else:
				movies = Movie.query.whoosh_search(session.get('query')).order_by(order_column + " " + order_dir).slice(int(start),int(start) + int(length))
				count_movies=Movie.query.whoosh_search(session.get('query')).count()

	# Let's fetch all the users, I will need them
	users = User.query.all()

	# Init the dictionnary
	dict_movie = { "draw": draw , "recordsTotal": count_movies, "recordsFiltered" : count_movies, "data": []}
	for cur_movie in movies:
		# Fetch the note for the logged user
		my_mark=None
		my_when="-"
		my_where=""
		my_comment=""

		# Calculate the average mark for each movie
		average_mark_query=db.session.query(db.func.avg(Mark.mark).label("average")).filter(Mark.movie_id==cur_movie.id).one()
		
		try:
			# Round the average mark for a better display
			average_mark=round(float(average_mark_query.average),2)
		except:
			# There is no average because no mark recorded
			average_mark="-"

		for cur_mark in cur_movie.marked_by_users:
			if cur_mark.user_id == g.user.id:
				my_mark=cur_mark.mark
				my_comment = cur_mark.comment

				# Convert the date object only if seen_when field is not null (Homework UC)
				if cur_mark.seen_when != None:
					my_when=str(cur_mark.seen_when.strftime("%Y"))

				my_where=cur_mark.seen_where

		# Fill a dictionnary with marks for all the others users
		dict_mark = {}
		dict_where = {}
		dict_when = {}
		dict_homework = {}
		dict_comments = {}
		for cur_user in users:
			dict_mark[cur_user.id]=None
			dict_comments[cur_user.id]=None
			dict_where[cur_user.id]="-"
			dict_when[cur_user.id]="-"
			dict_homework[cur_user.id]={ "when" : None, "who:" : None, "link" : url_for("add_homework",movie_id=cur_movie.id,user_id=cur_user.id)}
			for cur_mark in cur_movie.marked_by_users:
				if cur_mark.user.id == cur_user.id:
					dict_mark[cur_user.id]=cur_mark.mark		
					dict_where[cur_user.id]=cur_mark.seen_where
					dict_comments[cur_user.id]=cur_mark.comment
					dict_homework[cur_user.id]["when"]=str(cur_mark.homework_when)

					if cur_mark.homework_who_user != None:
						dict_homework[cur_user.id]["who"]=cur_mark.homework_who_user.nickname

					# Convert the date object only if seen_when field is not null (Homework UC)
					if cur_mark.seen_when != None:
						dict_when[cur_user.id]=str(cur_mark.seen_when.strftime("%Y"))

		# Create the json object for the datatable
		dict_movie["data"].append({"DT_RowData": { "link": url_for("show_movie",movie_id=cur_movie.id), "mark_link": url_for("mark_movie",movie_id_form=cur_movie.id),"homework_link": dict_homework},
		"id": cur_movie.id,"name": cur_movie.name, 
		"director": cur_movie.director,
		"average" : average_mark,
		"my_mark": my_mark, 
		"my_when": my_when,
		"my_where": my_where, 
		"my_comment": my_comment,
		"other_marks": dict_mark, 
		"other_where": dict_where,
		"other_when": dict_when,
		"other_comments": dict_comments,
		"other_homework_when" : dict_homework })

	# Send the json object to the browser
	return json.dumps(dict_movie) 

@app.route('/movies/show/<int:movie_id>')
@login_required
def show_movie(movie_id):
	# Select movie
	movie = Movie.query.get_or_404(movie_id)

	# Initialize the dict which will contain the data to be displayed
	mark_users=[]

	# Get user list
	users=User.query.all()

	# Init the form that will be used if we want to update the movie data
	update_movie_form=UpdateMovieForm(movie_id=movie.id)

	# Browse all users
	for cur_user in users:
		
		# Let's check if the movie has already been marked by the user
		marked_movie=Mark.query.get((cur_user.id,movie_id))

		if marked_movie != None:

			# Replace the seen_where letter by a nicer text
			if marked_movie.seen_where=="C":
				seen_where_text="Cinema"
			elif marked_movie.seen_where=="M":
				seen_where_text="Maison"

			# We are in homework mode if a user gave an homework AND the mark is still none
			# If not we are in mark mode
			if marked_movie.homework_who != None and marked_movie.mark == None:
				mark_users.append({ "user": cur_user, "mark": "homework_in_progress", "seen_where": None, "seen_when": None, "comment": None })
			else:
				mark_users.append({ "user": cur_user, "mark": marked_movie.mark, "seen_where": seen_where_text, "seen_when": marked_movie.updated_when.strftime("%d/%m/%Y") ,"comment": marked_movie.comment })
		else:
			mark_users.append({ "user" : cur_user, "mark": None, "seen_where": None, "seen_when": None, "comment": None })

	# Let's check if the movie has already been marked by the user
	marked_movie=Mark.query.get((g.user.id,movie_id))

	if marked_movie is None or marked_movie.mark == None:
		return render_template('movie_show.html', movie=movie, mark_users=mark_users, movie_next=movie.next(),movie_prev=movie.prev(),marked_flag=False,update_movie_form=update_movie_form)
	else:
		return render_template('movie_show.html', movie=movie, mark_users=mark_users, movie_next=movie.next(),movie_prev=movie.prev(),marked_flag=True, update_movie_form=update_movie_form)

@app.route('/movies/mark/<int:movie_id_form>', methods=['GET','POST'])
@login_required
def mark_movie(movie_id_form):
	# Select movie
	form=MarkMovieForm()
	movie = Movie.query.get_or_404(movie_id_form)

	# Let's check if the movie has already been marked
	marked_movie=Mark.query.get((g.user.id,movie_id_form))

	# Mark the movie and display the correct page
	if form.validate_on_submit():

		if marked_movie == None:
			# The movie has never been marked => Create the object
			marked_movie=Mark(user_id=g.user.id,
				movie_id=movie.id,
				seen_when=form.seen_when.data,
				seen_where=form.seen_where.data,
				mark=form.mark.data,
				comment=form.comment.data,
				updated_when=datetime.now()
			)	
	
			flash_message_success="Note ajoutée"
			notif_type="add"
		else:
			# Update Movie
			marked_movie.mark=form.mark.data
			marked_movie.comment=form.comment.data
			marked_movie.seen_when=form.seen_when.data
			marked_movie.seen_where=form.seen_where.data

			# If we mark an homework, let's set the date in order to be on the activity flow
			# Rating an homework mean there is an homework date but not a mark date
			if marked_movie.updated_when == None and marked_movie.homework_when != None:
				marked_movie.updated_when=datetime.now()
				flash_message_success="Devoir rempli"
				notif_type="homework"
			else:
				flash_message_success="Note mise à jour"
				notif_type="update"
		try:
			db.session.add(marked_movie)
			db.session.commit()
			flash(flash_message_success,'success')

			# Send notification
			mark_movie_notification(marked_movie,notif_type)
			return redirect(url_for('show_movie',movie_id=movie_id_form))
			
		except IntegrityError:
			db.session.rollback()
			flash('Impossible de noter le film','danger')
			return render_template('movie_show.html', movie=movie, mark=True, marked_flag=False, form=form)

		except FlushError:
			db.session.rollback()
			flash('Impossible de noter le film','danger')
			return render_template('movie_show.html', movie=movie, mark=True, marked_flag=False, form=form)

	if marked_movie is None or marked_movie.mark == None:
		return render_template('movie_show.html', movie=movie, mark=True, marked_flag=False, form=form)
	else:
		# Movie has already been marked => Fill the form with data
		form=MarkMovieForm(mark=marked_movie.mark,comment=marked_movie.comment,seen_when=marked_movie.seen_when,seen_where=marked_movie.seen_where)
		return render_template('movie_show.html', movie=movie, mark=True, marked_flag=True,form=form)

@app.route('/movies/add', methods=['GET','POST'])
@login_required
def add_movie():
	# First, generate all the forms that we going to use in the view
	search_form=SearchMovieForm() 

	# Render the template
	return render_template('add_movie_wizard.html', search_form=search_form, header_text=u"Ajout d'un film", endpoint="add")

@app.route('/movies/add/select/<int:page>', methods=['GET','POST'], endpoint="select_add_movie")
@app.route('/movies/add/select', methods=['POST'], endpoint="select_add_movie")
@app.route('/movies/update/select/<int:page>', methods=['GET','POST'], endpoint="select_update_movie")
@app.route('/movies/update/select', methods=['POST'], endpoint="select_update_movie")
@login_required
def select_movie(page=1):

	"""
		This functions fetch movies from the API using pagination system in order to avoid a timeout with the API
		and also a too long time execution due to an high movies number to fetch and display
	"""

	# Calculate endpoint
	endpoint=request.endpoint.split("_")[1]

	# Create a search form in order to get the search query from the search wizard step
	search_form=SearchMovieForm()

	# If we come from the search_movie for, put the query string into a session
	if search_form.search.data != None and search_form.search.data != "":
		query_movie=search_form.search.data
		session['query_movie'] = search_form.search.data
	else:
		query_movie=session.get('query_movie',None)

	# Check if we correctly do a search, if not => Let's go back to the add movie form
	if search_form.submit_search.data and not search_form.validate_on_submit():
		flash('Veuillez saisir une recherche !', 'warning')
		
		if endpoint == "add":
			header_text=u"Ajout d'un film"
		elif endpoint == "update":
			movie = session.get("movie")
			header_text=u"Mise à jour du film " + movie.name

		return render_template('add_movie_wizard.html', search_form=search_form, header_text=header_text,endpoint=endpoint)

	# If we are here and that there is nothing into query_string => There is an issue
	# Let's go back to the main form
	if query_movie == None:
		flash("Absence de chaine de recherche", 'danger')
		return redirect(url_for('add_movie'))

	# Fetch how many pages we have to handle
	total_pages = search_page_number(query_movie)

	# Check if the page number is correct
	if page < 1 or page > total_pages:
		flash("Page de resultat inexistante", 'danger')
		return redirect(url_for('add_movie'))

	# Pagination management
	if page - 1 >= 1:
		has_prev = True
	else:
		has_prev = False

	if page + 1 <= total_pages:
		has_next = True
	else:
		has_next = False

	# Fetch the query from the previous form in order to fill correctly the radio choices
	select_form=SelectMovieForm(search_movies(query_movie,page))
	session["page"] = page

	# Check if we have some results, if not tell the user that there is no matching results
	# and propose it to make a new search
	if total_pages == 1 and len(select_form.movie.choices) == 0:
		flash("Aucun résultat pour cette recherche", "warning")
		return redirect(url_for("add_movie"))

	return render_template('select_movie_wizard.html', select_form=select_form, cur_page=page, total_pages=total_pages, has_prev=has_prev, has_next=has_next,endpoint=endpoint)

@app.route('/movies/add/confirm', methods=['POST'], endpoint="confirm_add_movie")
@app.route('/movies/update/confirm', methods=['POST'], endpoint="confirm_update_movie")
@login_required
def confirm_movie():

	# Calculate endpoint
	endpoint=request.endpoint.split("_")[1]

	# Create the select form for validation
	select_form=SelectMovieForm()

	# Validate selection form
	if select_form.submit_select.data:

		# Fetch the query from the previous form in order to fill correctly the radio choices
		query_movie = session.get('query_movie', None)
		page = session.get('page', None)

		if query_movie != None and page != None:
			select_form=SelectMovieForm(search_movies(query_movie,page))

		# If we are here, we displayed the form once and we want to go to the wizard next step doing a form validation
		if select_form.validate_on_submit():
		
			# Last step : Set type and origin and add the movie
			# Note : Movie_id is the TMVDB id
			confirm_form=ConfirmMovieForm()

			movie_to_create=get_movie(select_form.movie.data)
			confirm_form.movie_id.data=select_form.movie.data

			if endpoint == "add":
				confirm_form.submit_confirm.label.text="Ajouter le film"
			elif endpoint == "update":
				confirm_form.submit_confirm.label.text=u"Mettre à jour le film"

			# Go to the final confirmation form
			return render_template('confirm_movie_wizard.html', movie=movie_to_create, form=confirm_form, endpoint=endpoint)

		else:
			return redirect(url_for('select_movie',page=page))

	# Create the form we're going to use	
	confirm_form=ConfirmMovieForm()

	# Confirmation form => add into the database
	if confirm_form.submit_confirm.data and confirm_form.validate_on_submit():

		if endpoint == "add":

			# Form is okay => We can add the movie
			movie_to_create=get_movie(confirm_form.movie_id.data)
			movie_to_create.added_by_user=g.user.id
			movie_to_create.type=confirm_form.type.data.id
			movie_to_create.origin=confirm_form.origin.data.id
			movie_to_create.added_when=datetime.now()

			# Add the movie in the database
			try:
				db.session.add(movie_to_create)
				db.session.flush()
				new_movie_id=movie_to_create.id
				db.session.commit()
				flash('Film ajouté','success')

				# Donwload the poster and update the database
				if download_poster(movie_to_create):
					flash('Affiche téléchargée','success')
				else:
					flash('Impossible de télécharger le poster','warning')

				# Movie has been added => Send notifications
				add_movie_notification(movie_to_create)
				
				# Movie added ==> Go to the mark form !
				return redirect(url_for('mark_movie',movie_id_form=new_movie_id))

			except IntegrityError as e:
				flash('Film déjà existant','danger')
				db.session.rollback()
				return redirect(url_for('add_movie'))

		elif endpoint == "update":
	
			# Form is okay => Fetch the movie and update it
			movie_id=session.get('movie_id',None)

			if movie_id == None:
				flash("Erreur générale","danger")
				return redirect(url_for("list_movies"))
			
			# If we are here, we have a usable movie_id value
			movie=Movie.query.get(movie_id)

			# If the movie_id is an incorrect value => Go back to the movie list
			# Don't go back to the movie file page since the movie_id is an incorrect value
			if movie == None:
				flash("Erreur générale","danger")
				return redirect(url_for("movies_list"))

			# All checks are okay => Update the movie !
			temp_movie=get_movie(confirm_form.movie_id.data)

			# Put the notifications into a dictionnary since I can't get 
			notification_data={}
			notification_data["old"]={ "name": movie.name,
					"release_date" : movie.release_date,
					"director" : movie.director,
					"type" : movie.type_object.type,
					"origin" : movie.origin_object.origin
					}

			# Update the object that will be stored in the database
			movie.name=temp_movie.name
			movie.release_date=temp_movie.release_date
			movie.url=temp_movie.url
			movie.tmvdb_id=temp_movie.tmvdb_id
			movie.director=temp_movie.director
			movie.overview=temp_movie.overview
			movie.duration=temp_movie.duration
			movie.poster_path=temp_movie.poster_path
			movie.type=confirm_form.type.data.id
			movie.origin=confirm_form.origin.data.id

			# Add the movie in the database
			try:
				db.session.add(movie)
				db.session.flush()
				db.session.commit()
				flash('Film mis à jour','success')

				# Donwload the poster and update the database
				if download_poster(movie):
					flash('Affiche téléchargée','success')
				else:
					flash('Impossible de télécharger le poster','warning')
				
				# Update the dictionnary with the update movie data
				notification_data["new"]={ "name": movie.name,
					"release_date" : movie.release_date,
					"director" : movie.director,
					"type" : movie.type_object.type,
					"origin" : movie.origin_object.origin,
					"id" : movie.id
					}

				# Movie has been updated => Send notifications
				update_movie_notification(notification_data)

				# Clear the session variables
				session.pop('movie')
				session.pop('movie_id')
				session.pop('query_movie')
				
				# Movie updated ==> Go to the movie page !
				return redirect(url_for('show_movie',movie_id=movie.id))

			except IntegrityError as e:
				flash('Film déjà existant','danger')
				db.session.rollback()
				return redirect(url_for('show_movie',movie_id=movie.id))

	# If no validation form is filled, go back to the wizard first step
	return redirect(url_for('add_movie')) 

@app.route('/movies/update',methods=['POST'])
@login_required
def update_movie():

	# Generate the list with the choices returned via the API
	update_movie_form=UpdateMovieForm()
	search_form=SearchMovieForm() 
	select_form=SelectMovieForm()
	confirm_form=ConfirmMovieForm()

	# We come from the movie file page 
	if update_movie_form.submit_update_movie.data and update_movie_form.validate_on_submit():

		# In stead of getting the query string, directly use the movie title from the database		
		movie=Movie.query.get_or_404(update_movie_form.movie_id.data)
		search_form.search.data=movie.name

		# Put into a session variable the movie id we want to update in order to do the final update on the last wizard step
		session['movie_id'] = movie.id

		# Put the object into the session array => We'll need it later
		session['movie']=movie

		return render_template('add_movie_wizard.html', search_form=search_form,header_text=u"Mise à jour de la fiche du film " + movie.name, endpoint="update")

	# Search form is validated => Let's fetch the movirs from tvdb.org
	if search_form.submit_search.data:

		# Get the movie object in order to get the movie name
		movie=session.get('movie',None)

		# Put it in a session in order to do the validation
		session['query_movie'] = search_form.search.data

		if search_form.validate_on_submit():
			select_form=SelectMovieForm(search_movies(search_form.search.data))

			# Display the selection form
			if len(select_form.movie.choices) == 0:
				flash("Aucun film correspondant","danger")
				return render_template('add_movie_wizard.html', search_form=search_form)
			else:
				return render_template('select_movie_wizard.html', select_form=select_form,url_wizard_next=url_for("update_movie"))
		else:
			return render_template('add_movie_wizard.html', search_form=search_form,header_text=u"Mise à jour de la fiche du film " + movie.name)

	# Validate selection form
	if select_form.submit_select.data:

		# Rebuild the RadioField list in order to be able to validate the form
		select_form=SelectMovieForm(search_movies(session.get('query_movie',None)))

		if select_form.validate_on_submit():
			# Update the origin using data stored in database and fetch from TMVDB
			movie=Movie.query.get(session.get('movie_id',None))
	
			# Populate a temp movie object which will be used for display the movie data got from tmvdb
			tmvdb_movie=get_movie(select_form.movie.data)
			
			# Fill the confirm_form with the correct values gotten from the mobie object	
			confirm_form=ConfirmMovieForm(origin=movie.origin_object,type=movie.type_object)
			confirm_form.movie_id.data=select_form.movie.data
		
			# Update the text button
			confirm_form.submit_confirm.label.text=u'Mettre à jour le film'

			# Go to the final confirmation form
			return render_template('confirm_movie_wizard.html', movie=tmvdb_movie,form=confirm_form,url_wizard_next=url_for("update_movie"))

		else:
			# Select Form Error => Display it again in order the user to correct the error
			flash("Veuillez sélectionenr un film","danger")
			return render_template('select_movie_wizard.html', select_form=select_form,url_wizard_next=url_for("update_movie"))


@app.route('/my/marks')
@app.route('/my/marks/<int:page>')
@login_required
def list_my_movies(page=1):
	marked_movies=Mark.query.filter_by(user_id=g.user.id).paginate(page,15,False)
	return render_template('marks.html', marked_movies=marked_movies)

@lm.user_loader
def load_user(id):
	return User.query.get(int(id))

@app.route('/users/add', methods=['GET','POST'])
@login_required
def add_user():
	form=AddUserForm()
	if form.validate_on_submit():
		# Form is okay => add the user
		# But salt the password before
		hashed_password=hashpw(form.password.data.encode('utf-8'),gensalt())
	
		# Now add the user into the database	
		user=User(nickname=form.username.data,password=hashed_password,email=form.email.data)
		try:
			db.session.add(user)
			db.session.commit()
			flash('Utilisateur ajouté')
		except IntegrityError:
			flash('Utilisateur déjà existant')
	return render_template('add_user_form.html', form=form)

@app.route('/my/profile', methods=['GET', 'POST'])
@login_required
def edit_user_profile():

	# Init the form
	form=UserForm()

	if form.validate_on_submit():
		# Update the User object
		g.user.email = form.email.data

		# Init the dictionnary if we don't have anyone (Null attribute in the database)
		if g.user.notifications == None:
			g.user.notifications = {}
		
		# Update the notification dictionnary
		g.user.notifications["notif_own_activity"] = form.notif_own_activity.data
		g.user.notifications["notif_movie_add"] = form.notif_movie_add.data
		g.user.notifications["notif_homework_add"] = form.notif_homework_add.data
		g.user.notifications["notif_mark_add"] = form.notif_mark_add.data

		# Update the avatar if we have to
		if 'upload_avatar' in request.files:
			new_avatar=request.files['upload_avatar']

			# Check if the image has the correct mimetype ==> If not,abort the update
			if new_avatar.content_type not in app.config['ALLOWED_MIMETYPES']:
				flash('Format d\'image incorrect',"danger")
				return redirect(url_for('edit_user_profile'))

			# Save the file using the nickname hash
			if new_avatar.filename != '':

				# Define the future old avatar to remove
				old_avatar = g.user.avatar

				# Generate the new avatar
				g.user.avatar = hashlib.sha256(g.user.nickname + str(int(time.time()))).hexdigest()
				new_avatar.save(os.path.join(app.config['AVATARS_FOLDER'], g.user.avatar ))
				
				# Resize the image
				if resize_avatar(os.path.join(app.config['AVATARS_FOLDER'], g.user.avatar)):

					# Try to remove the previous avatar
					try:
						os.remove(os.path.join(app.config['AVATARS_FOLDER'], old_avatar))
						flash("Avatar correctement mis à jour","success")
					except OSError,e:
						app.logger.error('Impossible de supprimer l\'avatar')
						app.logger.error(str(e))
				else:
					# Delete the new avatar and go back to the previous one
					flash("Impossible de redimensionner l\'image","success")
					g.user.avatar=old_avatar
					try:
						os.remove(os.path.join(app.config['AVATARS_FOLDER'], g.user.avatar))
					except OSError,e:
						app.logger.error('Impossible de supprimer le nouvel avatar')
						app.logger.error(str(e))
					
		# Let's do the update
		try:
			# Update the user
			db.session.add(g.user)
			db.session.commit()

			flash('Informations mises à jour','success')

		except Exception,e:
			print e
			flash('Impossible de mettre à jour l\'utilisateur', 'danger')

	else:
		# Init the form with the specific constructor in order to have the notifictions fields filled
		# Do it only when we don't validate the form
		form=UserForm(g.user)

	# Fetch the object for the current logged_in user
	return render_template('edit_profile.html',form=form,state="user")

@app.route('/my/password', methods=['GET', 'POST'])
@login_required
def change_user_password():

	# Init the form
	form=PasswordForm(obj=g.user)

	# Check the form and validation the password check is ok
	if form.validate_on_submit():
		# Let's fetch the password from the form
		g.user.password = hashpw(form.password.data.encode('utf-8'),gensalt())
		try:
			db.session.add(g.user)
			db.session.commit()
			flash('Mot de passe mis à jour','success')
		except:
			flash('Impossible de mettre à our le mot de passe', 'danger')
	
	# Fetch the object for the current logged_in user
	return render_template('edit_profile.html',form=form,state="password")

@app.route('/homework/add/<int:movie_id>/<int:user_id>')
@login_required
def add_homework(movie_id,user_id):
	
	# Create the mark object
	mark=Mark(user_id=user_id,movie_id=movie_id,homework_who=g.user.id,homework_when=datetime.now())

	# We want to add an homework => Set a session variable in order to tell to the list_movies table not cleaning the table
	session['clear_table']=False

	# Add the object to the database
	try:
		db.session.add(mark)
		db.session.commit()
		flash('Devoir ajouté','success')
	
	except Exception,e: 
		flash('Impossible de creer le devoir','danger')
		return redirect(url_for('list_movies'))

	# Send email notification
	mail_status = add_homework_notification(mark)
	if mail_status == 0:
		flash('Notification envoyée','success')
	elif mail_status == 1:
		flash('Erreur lors de l\'envoi de la notification','danger')
	elif mail_status == 2:
		flash('Aucune notification à envoyer','warning')

	return redirect(url_for('show_movie',movie_id=movie_id))

@app.route('/homework/delete/<int:movie_id>/<int:user_id>')
@login_required
def delete_homework(movie_id,user_id):

	# Check if the homework exists and if the user has the right to delete it
	# We can't delete the homework we didn't propose
	homework=Mark.query.get((user_id,movie_id))
	
	# Homework doesn't exists => Stop processing
	if homework == None:
		flash("Ce devoir n'existe pas", "danger")
		return redirect(url_for('list_homeworks'))

	# Is the user allowed to delete the homework
	if homework.homework_who != g.user.id:
		flash("Vous n'avez pas le droit de supprimer ce devoir", "danger")
		return redirect(url_for('list_homeworks'))

	# We are here => We have the right to delete the homework
	if homework.mark == None:
		# The user didn't mark the movie so we can delete the record
		try:
			db.session.delete(homework)
			db.session.commit()
			flash("Devoir annulé","success")
		except:
			flash("Impossible de supprimer la note","danger")
	else:
		# The user marked the movie so we can't delete the record => Set the homework fields to none
		homework.homework_when = None
		homework.homework_who = None
		
		try:
			db.session.add(homework)
			db.session.commit()
			flash("Devoir annulé","success")
		except:
			flash("Impossible d'annuler le devoir","danger")

	# When finished => Go back to the homework page
	return redirect(url_for('list_homeworks'))
		
@app.route('/homework/list',methods=['GET','POST'])
@login_required
def list_homeworks():

	# If we have a get request, we don't come fomr a form
	# ==> Let's clean session variables
	if request.method == "GET":	
		session.pop('my_homework_filter','None')
		session.pop('given_homework_filter','None')

	# Create the two forms for user filtering
	if session.get('my_homework_filter', None) != None:
		my_homework_filter_form=HomeworkForm(label_name=u'Donné par :',prefix=u"my",user_filter=User.query.get(session.get('my_homework_filter',None)))
	else:
		my_homework_filter_form=HomeworkForm(label_name=u'Donné par :',prefix=u"my")

	if session.get('given_homework_filter', None) != None:
		given_homework_filter_form=HomeworkForm(label_name=u"Donné à:",prefix=u"given",user_filter=User.query.get(session.get('given_homework_filter')))
	else:
		given_homework_filter_form=HomeworkForm(label_name=u"Donné à:",prefix=u"given")

	# Query generation considering from where we do come from
	# We sort the results first by null results in order to show
	# movies we have to rate and them movies which have been rated
	# For this query, we use a case statement
	# http://stackoverflow.com/questions/1347894/order-by-null-first-then-order-by-other-variable

	# Fetch homeworks given by a user
	if my_homework_filter_form.validate_on_submit():

		if my_homework_filter_form.user_filter.data != None:
			# Save the filter into a session variable => Will be used if we do a search in the other form
			session['my_homework_filter']=my_homework_filter_form.user_filter.data.id
			
			my_homeworks = Mark.query.join(Mark.movie).filter(and_(Mark.user_id == g.user.id, Mark.homework_who != None, Mark.homework_who == my_homework_filter_form.user_filter.data.id)).order_by(desc(case([(Mark.mark == None, 0)],1)),Movie.name)
		else:
			my_homeworks = Mark.query.join(Mark.movie).filter(and_(Mark.user_id == g.user.id, Mark.homework_who != None)).order_by(desc(case([(Mark.mark == None, 0)],1)),Movie.name)

	elif session.get('my_homework_filter', None) != None:
		my_homeworks = Mark.query.join(Mark.movie).filter(and_(Mark.user_id == g.user.id, Mark.homework_who != None, Mark.homework_who == session.get('my_homework_filter'))).order_by(desc(case([(Mark.mark == None, 0)],1)),Movie.name)
	else:
		my_homeworks = Mark.query.join(Mark.movie).filter(and_(Mark.user_id == g.user.id, Mark.homework_who != None)).order_by(desc(case([(Mark.mark == None, 0)],1)),Movie.name)

	
	# Fetch homeworks given to other users	
	if given_homework_filter_form.validate_on_submit():

		if given_homework_filter_form.user_filter.data != None:
			
			# Save the filter into a session variable => Will be used if we do a search in the other form
			session['given_homework_filter']=given_homework_filter_form.user_filter.data.id

			given_homeworks = Mark.query.join(Mark.movie).filter(and_(Mark.homework_who == g.user.id, Mark.homework_who != None, Mark.user_id == given_homework_filter_form.user_filter.data.id)).order_by(desc(case([(Mark.mark == None, 0)],1)),Movie.name)
		else:
			given_homeworks = Mark.query.join(Mark.movie).filter(and_(Mark.homework_who == g.user.id)).order_by(desc(case([(Mark.mark == None, 0)],1)),Movie.name)

	elif session.get('given_homework_filter', None) != None:
		given_homeworks = Mark.query.join(Mark.movie).filter(and_(Mark.homework_who == g.user.id, Mark.user_id == session.get('given_homework_filter'))).order_by(desc(case([(Mark.mark == None, 0)],1)),Movie.name)
	else:
		given_homeworks = Mark.query.join(Mark.movie).filter(Mark.homework_who == g.user.id).order_by(desc(case([(Mark.mark == None, 0)],1)),Movie.name)

	return render_template('list_homeworks.html',my_homeworks=my_homeworks,given_homeworks=given_homeworks,my_homework_filter_form=my_homework_filter_form,given_homework_filter_form=given_homework_filter_form)

@app.route('/graph/mark', endpoint="graph_by_mark")
@app.route('/graph/mark_percent', endpoint="graph_by_mark_percent")
@app.route('/graph/type', endpoint="graph_by_type")
@app.route('/graph/origin', endpoint="graph_by_origin")
@app.route('/graph/year', endpoint="graph_by_year")
@app.route('/graph/year_theater', endpoint="graph_by_year_theater")
@app.route('/graph/average_type', endpoint="average_by_type")
@app.route('/graph/average_origin', endpoint="average_by_origin")
@login_required
def show_graphs():

	# Retrieve the graph_list from the app context and use it in a local variable
	graph_list = app.config['GRAPH_LIST']

	# Identify prev and next graph
	for index_graph in range(len(graph_list)):
		if request.endpoint == graph_list[index_graph]["graph_endpoint"]:

			# Set the graph_title
			graph_title=graph_list[index_graph]["graph_label"]
	
			# Set the graph pagination
			if index_graph - 1 >= 0:
				prev_graph=graph_list[index_graph-1]
			else:
				prev_graph=None

			if index_graph + 1 < len(graph_list):
				next_graph=graph_list[index_graph+1]
			else:
				next_graph=None
			break;

	# Generate the correct data considering the route
	graph_to_generate=os.path.basename(request.url_rule.rule)

	# Variable initialization
	labels=[]
	data={}

	# Fetch all users
	users = User.query.all();

	if graph_to_generate == "mark":
		
		# Distributed marks graph
		graph_type="line"

		# Fill the labels_array with all marks possible
		for cur_mark in frange(0,20,0.5):
			labels.append(cur_mark)

		# Fill the dictionnary with distributed_marks by user
		for cur_user in users:
			data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
			for cur_mark in frange(0,20,0.5):
				data[cur_user.nickname]["data"].append(Mark.query.filter(Mark.mark==cur_mark,Mark.user_id==cur_user.id).count())

	if graph_to_generate == "mark_percent":
		
		# Distributed marks graph
		graph_type="line"

		# Fill the labels_array with all marks possible
		for cur_mark in frange(0,20,0.5):
			labels.append(cur_mark)


		# Fill the dictionnary with distributed_marks by user
		for cur_user in users:
			data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }

			# Set the percentage considering the total movies number seen for each user and not globally
			user_movies_count = Mark.query.filter(Mark.user_id==cur_user.id).count()

			for cur_mark in frange(0,20,0.5):
				percent = float((Mark.query.filter(Mark.mark==cur_mark,Mark.user_id==cur_user.id).count() * 100)) / float(user_movies_count)
				data[cur_user.nickname]["data"].append(round(percent,2))

	elif graph_to_generate == "type":

		# Distributed types graph
		graph_type="bar"

		# Fill the types_array with all the types stored into the database
		types = Type.query.all();
		for cur_type in types:
			labels.append(cur_type.type)

		# Fill the dictionnary with distributed_types by user
		for cur_user in users:
			data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
			for cur_type in types:
				data[cur_user.nickname]["data"].append(Mark.query.join(Mark.movie).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Movie.type==cur_type.id).count())
	
	elif graph_to_generate == "origin":

		# Distributed marks graph
		graph_type="bar"

		# Fill the origin_array with all the types stored into the database
		origins = Origin.query.all();
		for cur_origin in origins:
			labels.append(cur_origin.origin)

		# Fill the dictionnary with distributed_origins by user
		for cur_user in users:
			data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
			for cur_origin in origins:
				data[cur_user.nickname]["data"].append(Mark.query.join(Mark.movie).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Movie.origin==cur_origin.id).count())


	elif graph_to_generate == "average_type":

		# Average by type
		graph_type="radar"

		# Fill the types array with all the types stored into the database
		types = Type.query.all();
		for cur_type in types:
			labels.append(cur_type.type)

		# Fill the dictionnary with average mark by user and by type
		for cur_user in users:
			data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
			for cur_type in types:
				avg_query=db.session.query(db.func.avg(Mark.mark).label("average")).join(Mark.movie).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Movie.type==cur_type.id).one()
				
				# If no mark => Put null
				if avg_query.average == None:
					data[cur_user.nickname]["data"].append("null")
				else:
					data[cur_user.nickname]["data"].append(round(float(avg_query.average),2))

	elif graph_to_generate == "average_origin":

		# Average by type
		graph_type="radar"

		# Fill the origins array with all the origins stored into the database
		origins = Origin.query.all();
		for cur_origin in origins:
			labels.append(cur_origin.origin)

		# Fill the dictionnary with average mark by user and by type
		for cur_user in users:
			data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
			for cur_origin in origins:
				avg_query=db.session.query(db.func.avg(Mark.mark).label("average")).join(Mark.movie).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Movie.origin==cur_origin.id).one()
				
				# If no mark => Put null
				if avg_query.average == None:
					data[cur_user.nickname]["data"].append("null")
				else:
					data[cur_user.nickname]["data"].append(round(float(avg_query.average),2))

	elif graph_to_generate == "year":

		# Distributed movies graph by year
		graph_type="line"

		# Search the min and max year in order to generate a optimized graph
		min_year=int(db.session.query(db.func.min(Mark.seen_when).label("min_year")).one().min_year.strftime("%Y"))
		max_year=int(db.session.query(db.func.max(Mark.seen_when).label("max_year")).one().max_year.strftime("%Y"))

		for cur_year in range(min_year,max_year+1,1):
			labels.append(cur_year)

		# Fill the dictionnary with distributed_years by user
		for cur_user in users:
			data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : []}
			for cur_year in range(min_year,max_year+1,1):
				data[cur_user.nickname]["data"].append(Mark.query.filter(Mark.mark!=None,Mark.user_id==cur_user.id,db.func.year(Mark.seen_when)==cur_year).count())

	elif graph_to_generate == "year_theater":

		# Distributed movies graph by year
		graph_type="line"

		# Search the min and max year in order to generate a optimized graph
		min_year=int(db.session.query(db.func.min(Mark.seen_when).label("min_year")).one().min_year.strftime("%Y"))
		max_year=int(db.session.query(db.func.max(Mark.seen_when).label("max_year")).one().max_year.strftime("%Y"))

		for cur_year in range(min_year,max_year+1,1):
			labels.append(cur_year)

		# Fill the dictionnary with distributed_years by user
		for cur_user in users:
			data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : []}
			for cur_year in range(min_year,max_year+1,1):
				data[cur_user.nickname]["data"].append(Mark.query.filter(Mark.mark!=None,Mark.user_id==cur_user.id,Mark.seen_where=="C",db.func.year(Mark.seen_when)==cur_year).count())


	return render_template('show_graphs.html',graph_title=graph_title,graph_type=graph_type,labels=labels,data=data,prev_graph=prev_graph,next_graph=next_graph)

@app.route('/dashboard')
@login_required
def show_dashboard():

	# Variables declaration which will contains all the stats needed for the dashboard
	general_stats={}
	activity_list=[]
	stats_dict={}
	labels=[]
	data={"theaters": [], "others": []}
	
	# Fetch the last 20 last activity records
	activity_dict=get_activity_list(0,20)

	# Build a dictionnary with the average and movies count (global / only in theaters and only at home) for all users
	# We do a dictionnary instead of a global GROUP BY in order to have all users including the one without any mark
	# and also allow an easy access to a specific user which is nice for the dashboard display
	users=User.query.all()

	for cur_user in users:
		try:
			# Fetch the user object and the current average
			avg_query=db.session.query(db.func.avg(Mark.mark).label("average")).filter(Mark.mark!=None,Mark.user_id==cur_user.id).one()
			stats_dict[cur_user.id]={ "user": cur_user, "avg": round(float(avg_query.average),2), "movies_total" : 0, "movies_theaters" : 0, "movies_home": 0 }

		except TypeError:
			# If we are here, that means the user doesn't have an average (Maybe because no mark recorded)
			stats_dict[cur_user.id]={ "user": cur_user, "avg": "N/A",  "movies_total" : 0, "movies_theaters" : 0, "movies_home": 0 }

		# Let's count the movies for each user
		stats_dict[cur_user.id]["movies_total"] = Mark.query.filter(Mark.mark!=None,Mark.user_id==cur_user.id).count()
		stats_dict[cur_user.id]["movies_theaters"] = Mark.query.filter(Mark.mark!=None,Mark.user_id==cur_user.id,Mark.seen_where=="C").count() 
		stats_dict[cur_user.id]["movies_home"] = Mark.query.filter(Mark.mark!=None,Mark.user_id==cur_user.id,Mark.seen_where=="M").count() 

	# Fetch general databases statistics
	general_stats["movies"] = Movie.query.count()

	# Generate datas for the bar graph
	cur_year=datetime.now().strftime("%Y")
	
	# Set month in French
	locale.setlocale(locale.LC_ALL, "fr_FR.UTF-8")
	for cur_month in range(1,13,1):
		labels.append(datetime.strptime(str(cur_month), "%m").strftime("%B").decode('utf-8'))
		data["theaters"].append(Mark.query.filter(Mark.mark!=None,Mark.user_id==g.user.id,Mark.user_id==g.user.id,Mark.seen_where=="C",db.func.month(Mark.seen_when)==cur_month,db.func.year(Mark.seen_when)==cur_year).count())
		data["others"].append(Mark.query.filter(Mark.mark!=None,Mark.user_id==g.user.id,Mark.user_id==g.user.id,Mark.seen_where=="M",db.func.month(Mark.seen_when)==cur_month,db.func.year(Mark.seen_when)==cur_year).count())

	# Go back to default locale
	locale.setlocale(locale.LC_ALL,locale.getdefaultlocale())
	
	return render_template('show_dashboard.html', activity_list=activity_dict["list"], general_stats=general_stats,labels=labels,data=data,cur_year=cur_year,stats_dict=stats_dict)

@app.route('/activity/show')
@login_required
def show_activity_flow():
	return render_template('show_activity_flow.html')

@app.route('/activity/update', methods=['POST'])
@login_required
def update_activity_flow():
	
	# Local variables for handling the datatable
	args = json.loads(request.values.get("args"))
	columns = args.get("columns")
	start = args.get('start')
	length = args.get('length')
	draw = args.get('draw')

	# Fetch the activity items
	temp_activity_dict=get_activity_list(start,length)

	# Initialize dict which will contains that presented to the datatable
	activity_dict = { "draw": draw , "recordsTotal": temp_activity_dict["count"], "recordsFiltered" : temp_activity_dict["count"], "data": []}

	# Let's fill the activity_dict with data good format for the datatable
	for cur_activity in temp_activity_dict["list"]:
		if cur_activity["entry_type"] == "movies":
			entry_type="<a class=\"disabled btn btn-danger btn-xs\">Entrée</a>"

			# Sometimes, the user can be Null (Especially after an import
			# So, we need to put a default user in order to avoid a NoneType Exception
			if cur_activity["object"].added_by == None:
				user="CineBot"
			else:
				user=cur_activity["object"].added_by.nickname

			# Define the text that will be shown on the datatable
		        entry_text="Le film <a href=\"" +  url_for('show_movie', movie_id=cur_activity["object"].id) + "\">" + cur_activity["object"].name + u"</a> vient d'être ajouté par " + user

		elif cur_activity["entry_type"] == "marks":
			entry_type="<a class=\"disabled btn btn-primary btn-xs\">Note</a>"	

			# Sometimes, the comment can be Null (Especially after an import
			# So, we need to put a default user in order to avoid a NoneType Exception
			if cur_activity["object"].comment == None:
				comment=""
			else:
				comment=cur_activity["object"].comment

			# Precise if this is a mark for an homework or a simple mark
			if cur_activity["object"].updated_when != None and cur_activity["object"].homework_when != None:

				entry_type+=" <a class=\"disabled btn btn-warning btn-xs\">Devoir</a>"	

				# Define the text that will be shown on the datatable
				entry_text=cur_activity["object"].user.nickname + u" vient de remplir son devoir sur le film <a href=\"" + url_for('show_movie', movie_id=cur_activity["object"].movie_id) +"\">" +  cur_activity["object"].movie.name + "</a> .La note est de <span title=\"Commentaire\" data-toggle=\"popover\" data-placement=\"top\" data-trigger=\"hover\" data-content=\"" + comment + "\"><strong>" + str(cur_activity["object"].mark) +"</strong></span>"

			else:
				# Define the text that will be shown on the datatable
				entry_text=cur_activity["object"].user.nickname + u" a noté le film <a href=\"" + url_for('show_movie', movie_id=cur_activity["object"].movie_id) +"\">" +  cur_activity["object"].movie.name + "</a> avec la note <span title=\"Commentaire\" data-toggle=\"popover\" data-placement=\"top\" data-trigger=\"hover\" data-content=\"" + comment + "\"><strong>" + str(cur_activity["object"].mark) +"</strong></span>"

		elif cur_activity["entry_type"] == "homeworks":
			entry_type="<a class=\"disabled btn btn-warning btn-xs\">Devoir</a>"

			# Define the text that will be shown on the datatable
			entry_text=cur_activity["object"].homework_who_user.nickname + " vient de donner <a href=\"" + url_for('show_movie', movie_id=cur_activity["object"].movie_id) + "\">" +  cur_activity["object"].movie.name + "</a> en devoir a " + cur_activity["object"].user.nickname

		# Append the processed entry to the dictionnary that will be used by the datatable
		activity_dict["data"].append({"entry_type" : entry_type, "entry_text" : entry_text })

	# Return the dictionnary as a JSON object
	return json.dumps(activity_dict)
