# -*- coding: utf-8 -*-

from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
from builtins import next
from builtins import str
from builtins import range
import urllib.request, urllib.parse, urllib.error, hashlib, re, os, locale, json, copy, time,html2text
from datetime import datetime
from flask import render_template, flash, redirect, url_for, g, request, session, abort
from flask_login import login_user, logout_user, current_user, login_required
from flask_wtf import Form
from wtforms.ext.sqlalchemy.orm import model_form
from wtforms.ext.sqlalchemy.fields import QuerySelectField
from cineapp import app, db, lm
from cineapp.forms import LoginForm, AddUserForm, AddShowForm, MarkShowForm, SearchShowForm, SelectShowForm, ConfirmShowForm, FilterForm, UserForm, PasswordForm, HomeworkForm, UpdateShowForm, DashboardGraphForm
from cineapp.models import User, Show, Mark, Origin, Type, FavoriteShow, FavoriteType, PushNotification
from cineapp.tvmdb import search_shows,get_show,download_poster, search_page_number
from cineapp.emails import add_show_notification, mark_show_notification, add_homework_notification, update_show_notification
from cineapp.utils import frange, get_activity_list, resize_avatar
from cineapp.push import notification_unsubscribe
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm.exc import FlushError
from sqlalchemy import desc, or_, and_, Table, text
from sqlalchemy.sql.expression import select, case, literal
from bcrypt import hashpw, gensalt
from werkzeug.utils import secure_filename
from random import randint
from cineapp.slack import slack_mark_notification
from cineapp.auth import guest_control

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
        g.search_form = SearchShowForm(prefix="search")

        # Make the graph list available in the whole app
        g.graph_list = app.config['GRAPH_LIST']

        # Return the current date
        g.cur_date = datetime.now()

        # Define the mode (Movie or TVShow)
        g.app_mode = "tv"
        g.tvmdb_api_mode = "tv"

        # Set mode to movies by default
        if session.get('show_type') == None:
            app.logger.info("Le type de show n'est pas défini dans la session. Configuration à movies par défaut")
            session["show_type"] = "movies"
       
        # Configure g with the value stored in the session
        # TIP: g is only set for the current request and not globally to the session
        # For that: there is ... session
        g.show_type=session["show_type"]

@app.route('/login', methods=['GET','POST'])
def login():

        # Let's check if we are authenticated => If yes redirect to the index page
        if g.user is not None and g.user.is_authenticated:
                return redirect(url_for('show_dashboard'))

        # If we are here, we are not login. Build the form and try the login.
        form = LoginForm()
        if form.validate_on_submit():

                # Let's validate the user
                if form.username.data == "guest" and form.password.data == "guest":
                        user = User(guest=True)
                        # User authenticated => Let's login it
                        login_user(user)
                        return redirect(request.args.get('next') or url_for('list_movies'))

                user=User.query.filter_by(nickname=form.username.data).first()
                if user is None:
                        flash("Mauvais utilisateur !",'danger')
                        return redirect(url_for('login'))
                else:
                        if hashpw(form.password.data.encode('utf-8'), user.password.encode('utf-8')).decode('utf-8') != user.password:
                                flash("Mot de passe incorrect !",'danger')
                                return redirect(url_for('login'))

                        # User authenticated => Let's login it
                        login_user(user)

                        # Let's write user nickname in the session (Will be user for the chat feature)
                        # We need to use a session since g object is not available because before_request is not executed on sockets event
                        session["user"] = user

                        return redirect(request.args.get('next') or url_for('index'))
                return redirect(url_for('index'))
        
        return render_template('login.html', title='Sign In', form=form)

@app.route('/logout')
def logout():
        logout_user()

        # Purge all the subscriptions objects from the current session
        subscriptions_to_delete=PushNotification.query.filter(PushNotification.session_id==session.sid).all()
        for cur_subscription in subscriptions_to_delete:
                notification_unsubscribe(cur_subscription)

        return redirect(url_for('index'))

@app.route('/switch/<show_type>')
def switch_show_type(show_type):

    # Check if the URL is allowed or not
    if show_type not in [ "movies", "tvshows" ]:
        app.logger.error("Le mode %s n'est pas autorisé" % show_type)
    else:
        app.logger.info("Bascule vers le mode: %s" % show_type)
        session["show_type"]=show_type

    return redirect(url_for('index'))

@app.route('/movies/json', methods=['GET','POST'])
@login_required
def update_datatable():

        app.logger.info('Entering update_datatables function')

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
                elif m.group(1) == "favs":
                        filter_field = FavoriteType.star_weight
                        
        # Filtering by logged user mark
        elif order_column == "my_mark":
                filter_user = g.user.id
                filter_field = Mark.mark

        # Filtering by logged user seen date
        elif order_column == "my_when":
                filter_user = g.user.id
                filter_field = Mark.seen_when

        # Filtering by favorite
        elif order_column == "my_fav":
                filter_user = g.user.id
                filter_field = FavoriteType.star_weight
        else:
                filter_user = None

        # If we enter here, we are going to filter by user (my_* column or others_* column)     
        if filter_user != None:

                app.logger.info('Entering filter_user is not Null')

                # Let's build the filtered requested following what has been posted in the filter form
                filter_fields=session.get('query')

                # If we must sort by favorite, the query is not the same. Let's generate here   
                if filter_field == FavoriteType.star_weight:

                        # We only want movies with favorite defined for the concerned user
                        movies_query = Show.query.outerjoin(Mark).outerjoin(FavoriteShow).filter(FavoriteShow.user_id==filter_user).outerjoin(FavoriteType)
                else:
                        # All the others sorts refer to the Mark.user_id column
                        movies_query = Show.query.outerjoin(Mark).outerjoin(FavoriteShow).filter(Mark.user_id==filter_user).outerjoin(FavoriteType)

                # Check that we have a real list in order to avoid an exception 
                if isinstance(filter_fields,dict):
                        if filter_fields['origin'] != None:
                                movies_query = movies_query.filter(Show.origin==filter_fields['origin'])

                        if filter_fields['type'] != None:
                                movies_query = movies_query.filter(Show.type==filter_fields['type'])

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
                                        array_movies_seen_in_theater.append(cur_movie_seen_in_theater.show_id)
                                
                                # Finally let's build the filter that will be used later building the query
                                movies_query = movies_query.filter(Mark.show_id.in_(array_movies_seen_in_theater))

                        if filter_fields['favorite'] !=None:

                                # Same behaviour than the previous one
                                favorite_movies = FavoriteShow.query.filter(FavoriteShow.user_id == filter_fields['favorite']).all()
                                favorite_movies_array = []

                                for cur_favorite_movie in favorite_movies:
                                        favorite_movies_array.append(cur_favorite_movie.show_id)

                                movies_query = movies_query.filter(FavoriteShow.show_id.in_(favorite_movies_array))

                # Sort my desc marks
                if order_dir == "desc":
                        if session.get('search_type') == 'list': 
                                movies = movies_query.filter(filter_field != None).order_by(desc(filter_field)).slice(int(start),int(start) + int(length))
                                count_movies=movies_query.count()

                        elif session.get('search_type') == 'filter_origin_type':
                                movies = movies_query.filter(filter_field != None).order_by(desc(filter_field)).slice(int(start),int(start) + int(length))
                                count_movies=movies_query.filter(Mark.mark != None).count()
                                        
                        elif session.get('search_type') == 'filter':
                                movies = movies_query.msearch(session.get('query'),fields=["name","original_name","director"]).filter(filter_field != None).order_by(desc(filter_field)).slice(int(start),int(start) + int(length))
                                count_movies=movies_query.msearch(session.get('query'),fields=["name","original_name","director"]).filter(filter_field != None).count()

                # Sort by asc marks
                else:
                        if session.get('search_type') == 'list': 
                                movies = movies_query.filter(filter_field != None).order_by(filter_field).slice(int(start),int(start) + int(length))
                                count_movies=movies_query.count()
                        elif session.get('search_type') == 'filter_origin_type':
                                movies = movies_query.filter(filter_field != None).order_by(filter_field).slice(int(start),int(start) + int(length))
                                count_movies=movies_query.filter(filter_field != None).count()
                        elif session.get('search_type') == 'filter':
                                movies = movies_query.msearch(session.get('query'),fields=["name","original_name","director"]).filter(filter_field != None).order_by(filter_field).slice(int(start),int(start) + int(length))
                                count_movies=movies_query.msearch(session.get('query'),fields=["name","original_name","director"]).count()
        else:

                app.logger.info('Entering filter_user is Null')

                # If we are here => No sort by user but only global sort or no sort
                if session.get('search_type') == 'list': 
                        app.logger.info('Entering list search_type')
                        if order_column == "average":
                                if order_dir == "desc":
                                        movies=db.session.query(Show).join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(desc(db.func.avg(Mark.mark))).slice(int(start),int(start) + int(length))
                                else:
                                        movies=db.session.query(Show).join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).slice(int(start),int(start) + int(length))
                                
                                count_movies=db.session.query(Show).join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).count()
                        else:
                                movies = Show.query.order_by(text(order_column,order_dir)).slice(int(start),int(start) + int(length))
                                count_movies=Show.query.count()

                # Let's use the filter form
                elif session.get('search_type') == 'filter_origin_type':
                        app.logger.info('Entering list filter_origin_type')
                        # Let's build the filtered requested following what has been posted in the filter form
                        filter_fields=session.get('query')
                        movies_query = Show.query.outerjoin(Mark).outerjoin(FavoriteShow)

                        if filter_fields['origin'] != None:
                                movies_query = movies_query.filter(Show.origin==filter_fields['origin'])

                        if filter_fields['type'] != None:
                                movies_query = movies_query.filter(Show.type==filter_fields['type'])

                        if filter_fields['seen_where'] !=None:
                                movies_query = movies_query.filter(Mark.user_id==filter_fields['seen_where']).filter(Mark.seen_where=='C')

                        if filter_fields['favorite'] !=None:
                                movies_query = movies_query.filter(FavoriteShow.user_id==filter_fields['favorite'])

                        # Build the request
                        if order_column == "average":
                                if order_dir == "desc":
                                        app.logger.info("Requete par moyenne desecendante")
                                        movies=movies_query.group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(desc(db.func.avg(Mark.mark))).slice(int(start),int(start) + int(length)).all()
                                else:
                                        app.logger.info("Requete par moyenne ascendante")
                                        movies=movies_query.group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).slice(int(start),int(start) + int(length)).all()
                        else:
                                movies = movies_query.order_by(text(order_column,order_dir)).slice(int(start),int(start) + int(length))

                        count_movies=movies_query.count()

                # Here, this is for the string search (Show or director)
                elif session.get('search_type') == 'filter':
                        app.logger.info('Entering list filter')
                        if order_column == "average":
                                if order_dir == "desc":
                                        movies=Show.query.msearch(session.get('query'),fields=["name","original_name","director"]).join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(desc(db.func.avg(Mark.mark))).slice(int(start),int(start) + int(length)).all()
                                else:
                                        movies=Show.query.msearch(session.get('query'),fields=["name","original_name","director"]).join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).slice(int(start),int(start) + int(length)).all()
                                count_movies=Show.query.msearch(session.get('query'),fields=["name","original_name","director"]).join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).count()
                        else:
                                movies = Show.query.msearch(session.get('query'),fields=["name","original_name","director"]).order_by(text(order_column,order_dir)).slice(int(start),int(start) + int(length))
                                count_movies=Show.query.msearch(session.get('query'),fields=["name","original_name","director"]).count()

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
                my_fav=None

                # Calculate the average mark for each movie
                average_mark_query=db.session.query(db.func.avg(Mark.mark).label("average")).filter(Mark.show_id==cur_movie.id).one()
                
                try:
                        # Round the average mark for a better display
                        average_mark=round(float(average_mark_query.average),2)
                except:
                        # There is no average because no mark recorded
                        average_mark="-"

                # Get the cur_mark for the user
                for cur_mark in cur_movie.marked_by_users:
                        if cur_mark.user_id == g.user.id:
                                my_mark=cur_mark.mark

                                # Escape characters correctly for correct display in hover event
                                if cur_mark.comment != None:
                                        my_comment=cur_mark.comment.replace('"','\'')
                                else:
                                        my_comment=cur_mark.comment

                                # Convert the date object only if seen_when field is not null (Homework UC)
                                if cur_mark.seen_when != None:
                                        my_when=str(cur_mark.seen_when.strftime("%Y"))

                                my_where=cur_mark.seen_where

                # Check if the user has set the movie as favorite
                tmp_fav = [x for x in cur_movie.favorite_users if x.user_id == g.user.id]
                if len(tmp_fav) != 0:
                        my_fav = tmp_fav[0].star_type

                # Fill a dictionnary with marks for all the others users
                dict_mark = {}
                dict_where = {}
                dict_when = {}
                dict_homework = {}
                dict_comments = {}
                dict_favs = {}
                for cur_user in users:
                        dict_mark[cur_user.id]=None
                        dict_comments[cur_user.id]=None
                        dict_where[cur_user.id]="-"
                        dict_when[cur_user.id]="-"
                        dict_favs[cur_user.id]=None
                        dict_homework[cur_user.id]={ "when" : None, "who:" : None, "link" : url_for("add_homework",show_id=cur_movie.id,user_id=cur_user.id)}
                        for cur_mark in cur_movie.marked_by_users:
                                if cur_mark.user.id == cur_user.id:
                                        dict_mark[cur_user.id]=cur_mark.mark            
                                        dict_where[cur_user.id]=cur_mark.seen_where

                                        # Escape characters correctly for correct display in hover event
                                        if cur_mark.comment != None:
                                                dict_comments[cur_user.id]=cur_mark.comment.replace('"','\'')
                                        else:
                                                dict_comments[cur_user.id]=cur_mark.comment

                                        dict_homework[cur_user.id]["when"]=str(cur_mark.homework_when)

                                        if cur_mark.homework_who_user != None:
                                                dict_homework[cur_user.id]["who"]=cur_mark.homework_who_user.nickname

                                        # Convert the date object only if seen_when field is not null (Homework UC)
                                        if cur_mark.seen_when != None:
                                                dict_when[cur_user.id]=str(cur_mark.seen_when.strftime("%Y"))

                        # Check if the user has set the movie as favorite
                        tmp_fav = [x for x in cur_movie.favorite_users if x.user_id == cur_user.id]
                        if len(tmp_fav) != 0:
                                dict_favs[cur_user.id]=tmp_fav[0].star_type

                # Create the json object for the datatable
                dict_movie["data"].append({"DT_RowData": { "link": url_for("show_movie",show_id=cur_movie.id), "mark_link": url_for("mark_movie",show_id_form=cur_movie.id),"homework_link": dict_homework},
                "id": cur_movie.id,"name": cur_movie.name, 
                "director": cur_movie.director,
                "average" : average_mark,
                "my_mark": my_mark, 
                "my_when": my_when,
                "my_where": my_where, 
                "my_comment": my_comment,
                "my_fav": my_fav,
                "other_marks": dict_mark, 
                "other_where": dict_where,
                "other_when": dict_when,
                "other_comments": dict_comments,
                "other_favs": dict_favs,
                "other_homework_when" : dict_homework })

        # Send the json object to the browser
        return json.dumps(dict_movie) 

@app.route('/movies/show/random')
@login_required
def show_movie_random():
        """
                Function that redirects to a random movie sheet
        """
        # Get the movie number stored in the databaese
        count = Show.query.count()

        # Get the random id
        random_id = randint(1,count)

        # Check if the movie exists
        while Show.query.get(random_id) is None:
                random_id = randint(1,count)

        # Redirect to the movie sheet selected randomly
        return redirect(url_for('show_movie',show_id=random_id))

@app.route('/movies/mark/publish/<int:show_id>', methods=['GET'])
@login_required
@guest_control
def publish_mark(show_id):

        # Fetch the current comment for the logged user and send it on flask
        # Let's do that only if there is a mark to send
        mark = Mark.query.get_or_404((g.user.id,show_id))

        # Convert the HTML content to text in order to have a nice display in the mail
        html_converter = html2text.HTML2Text()
        mark.comment=html_converter.handle(mark.comment).strip()

        # Send notification
        if mark != None:
                if g.user.notifications["notif_slack"] and form.submit_mark_slack.data:
                        slack_result = slack_mark_notification(mark,app)
                        if slack_result == 0:
                                flash('Note envoyée sur Slack','success')
                        elif slack_result == -1:
                                flash('Notifications Slack désactivées','warning')
                        else:
                                flash('Impossible d\'envoyer la note sur Slack','danger')
                return redirect(url_for('show_movie',show_id=show_id))


@app.route('/my/marks/<int:page>')
@login_required
@guest_control
def list_my_movies(page=1):
        marked_movies=Mark.query.filter_by(user_id=g.user.id).paginate(page,15,False)
        return render_template('marks.html', marked_movies=marked_movies)

@lm.user_loader
def load_user(id):
        if id == "-1":
                user = User(guest=True)
                return user
        else:
                return User.query.get(int(id))

@app.route('/users/add', methods=['GET','POST'])
@login_required
@guest_control
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
@guest_control
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
                g.user.notifications["notif_comment_add"] = form.notif_comment_add.data
                g.user.notifications["notif_favorite_update"] = form.notif_favorite_update.data
                g.user.notifications["notif_chat_message"] = form.notif_chat_message.data
                g.user.notifications["notif_slack"] = form.notif_slack.data

                # Update the avatar if we have to
                if 'upload_avatar' in request.files:
                        new_avatar=request.files['upload_avatar']

                        # Save the file using the nickname hash
                        if new_avatar.filename != '':

                                # Check if the image has the correct mimetype ==> If not,abort the update
                                if new_avatar.content_type not in app.config['ALLOWED_MIMETYPES']:
                                        flash('Format d\'image incorrect',"danger")
                                        return redirect(url_for('edit_user_profile'))

                                # Define the future old avatar to remove
                                old_avatar = g.user.avatar

                                # Generate the new avatar
                                g.user.avatar = hashlib.sha256((g.user.nickname + str(int(time.time()))).encode('utf-8')).hexdigest()
                                new_avatar.save(os.path.join(app.config['AVATARS_FOLDER'], g.user.avatar ))

                                # Resize the image
                                if resize_avatar(os.path.join(app.config['AVATARS_FOLDER'], g.user.avatar)):

                                        # Try to remove the previous avatar
                                        try:
                                                if old_avatar != None:
                                                        os.remove(os.path.join(app.config['AVATARS_FOLDER'], old_avatar))

                                                flash("Avatar correctement mis à jour","success")
                                        except OSError as e:
                                                app.logger.error('Impossible de supprimer l\'avatar')
                                                app.logger.error(str(e))
                                else:
                                        # Delete the new avatar and go back to the previous one
                                        flash("Impossible de redimensionner l\'image","success")
                                        try:
                                                os.remove(os.path.join(app.config['AVATARS_FOLDER'], g.user.avatar))
                                        except OSError as e:
                                                app.logger.error('Impossible de supprimer le nouvel avatar')
                                                app.logger.error(str(e))
        
                                        # Reuse the old avatar
                                        g.user.avatar=old_avatar
                                        
                # Let's do the update
                try:
                        # Update the user
                        db.session.add(g.user)
                        db.session.commit()

                        flash('Informations mises à jour','success')

                except Exception as e:
                        print(e)
                        flash('Impossible de mettre à jour l\'utilisateur', 'danger')

        else:
                # Init the form with the specific constructor in order to have the notifictions fields filled
                # Do it only when we don't validate the form
                form=UserForm(g.user)

        # Fetch the object for the current logged_in user
        return render_template('edit_profile.html',form=form,state="user")

@app.route('/my/password', methods=['GET', 'POST'])
@login_required
@guest_control
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

@app.route('/homework/add/<int:show_id>/<int:user_id>')
@login_required
@guest_control
def add_homework(show_id,user_id):
        
        # Create the mark object
        mark=Mark(user_id=user_id,show_id=show_id,homework_who=g.user.id,homework_when=datetime.now())

        # We want to add an homework => Set a session variable in order to tell to the list_movies table not cleaning the table
        session['clear_table']=False

        # Add the object to the database
        try:
                db.session.add(mark)
                db.session.commit()
                flash('Devoir ajouté','success')
        
        except Exception as e: 
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

        return redirect(url_for('show_movie',show_id=show_id))

@app.route('/homework/delete/<int:show_id>/<int:user_id>')
@login_required
@guest_control
def delete_homework(show_id,user_id):

        # Check if the homework exists and if the user has the right to delete it
        # We can't delete the homework we didn't propose
        homework=Mark.query.get((user_id,show_id))
        
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
@guest_control
def list_homeworks():

        # Create the form
        homework_filter_form=HomeworkForm(to_user_filter=g.user)

        # Intialize the SQL query
        # We sort the results first by null results in order to show
        # movies we have to rate and them movies which have been rated
        # For this query, we use a case statement
        # http://stackoverflow.com/questions/1347894/order-by-null-first-then-order-by-other-variable
        homework_query = Mark.query.join(Mark.movie).order_by(case([(Mark.mark == None, 0)],else_=1),Show.name).filter(Mark.homework_who != None)

        # Fetch the homeworks
        if homework_filter_form.validate_on_submit():

                # Build the request considering the used fields
                if homework_filter_form.from_user_filter.data != None:
                        homework_query = homework_query.filter(Mark.homework_who == homework_filter_form.from_user_filter.data.id)

                if homework_filter_form.to_user_filter.data != None:
                        homework_query = homework_query.filter(Mark.user_id == homework_filter_form.to_user_filter.data.id)
                        
                homeworks=homework_query
        else:
                homeworks=homework_query.filter(and_(Mark.user_id == g.user.id))

        return render_template('list_homeworks.html',homework_filter_form=homework_filter_form,homeworks=homeworks)

@app.route('/graph/mark', endpoint="graph_by_mark")
@app.route('/graph/mark_percent', endpoint="graph_by_mark_percent")
@app.route('/graph/mark_interval', endpoint="graph_by_mark_interval")
@app.route('/graph/type', endpoint="graph_by_type")
@app.route('/graph/origin', endpoint="graph_by_origin")
@app.route('/graph/year', endpoint="graph_by_year")
@app.route('/graph/year_theater', endpoint="graph_by_year_theater")
@app.route('/graph/average_type', endpoint="average_by_type")
@app.route('/graph/average_origin', endpoint="average_by_origin")
@app.route('/graph/average_by_year', endpoint="average_by_year")
@login_required
@guest_control
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

                for cur_mark in frange(0,20,0.5):
                        labels.append(cur_mark)

                # Fill the dictionnary with distributed_marks by user
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
                        for cur_mark in frange(0,20,0.5):
                                data[cur_user.nickname]["data"].append(Mark.query.filter(Mark.mark==cur_mark,Mark.user_id==cur_user.id).count())

        if graph_to_generate == "mark_interval":

                range_mark_array=[]
                
                # Distributed marks graph
                graph_type="line"

                for cur_mark in frange(0,20,0.5):
                        range_mark_array.append(cur_mark)
        
                # Fille the label array
                for cur_index in range(0,len(range_mark_array)):
                        if cur_index < len(range_mark_array)-1:
                                labels.append(str(range_mark_array[cur_index]) + " - " + str(range_mark_array[cur_index+1]))
                        else:
                                labels.append(str(range_mark_array[cur_index]))

                print(labels)

                # Fill the dictionnary with distributed_marks by user
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
                        for cur_index in range(0,len(range_mark_array)):
                                if cur_index < len(range_mark_array)-1:
                                        data[cur_user.nickname]["data"].append(Mark.query.filter(Mark.mark>=range_mark_array[cur_index],Mark.mark<range_mark_array[cur_index+1],Mark.user_id==cur_user.id).count())
                                else:
                                        data[cur_user.nickname]["data"].append(Mark.query.filter(Mark.mark>=range_mark_array[cur_index],Mark.user_id==cur_user.id).count())

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
                                data[cur_user.nickname]["data"].append(Mark.query.join(Mark.movie).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Show.type==cur_type.id).count())
        
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
                                data[cur_user.nickname]["data"].append(Mark.query.join(Mark.movie).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Show.origin==cur_origin.id).count())


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
                                avg_query=db.session.query(db.func.avg(Mark.mark).label("average")).join(Mark.movie).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Show.type==cur_type.id).one()
                                
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
                                avg_query=db.session.query(db.func.avg(Mark.mark).label("average")).join(Mark.movie).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Show.origin==cur_origin.id).one()
                                
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

        elif graph_to_generate == "average_by_year":

                # Average by year
                graph_type="line"

                # Search the min and max year in order to generate a optimized graph
                min_year=int(db.session.query(db.func.min(Mark.seen_when).label("min_year")).one().min_year.strftime("%Y"))
                max_year=int(db.session.query(db.func.max(Mark.seen_when).label("max_year")).one().max_year.strftime("%Y"))

                for cur_year in range(min_year,max_year+1,1):
                        labels.append(cur_year)

                # Fill the dictionnary with average mark for each user by year
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : []}
                        for cur_year in range(min_year,max_year+1,1):
                                avg_query=db.session.query(db.func.avg(Mark.mark).label("average")).filter(Mark.mark!=None,Mark.user_id==cur_user.id,db.func.year(Mark.seen_when)==cur_year).one()

                                # If no mark => Put null
                                if avg_query.average == None:
                                        data[cur_user.nickname]["data"].append("null")
                                else:
                                        data[cur_user.nickname]["data"].append(round(float(avg_query.average),2))

        return render_template('show_graphs.html',graph_title=graph_title,graph_type=graph_type,labels=labels,data=data,prev_graph=prev_graph,next_graph=next_graph)

@app.route('/dashboard')
@login_required
@guest_control
def show_dashboard():

        print("KIKOOOOO")
        print(g.show_type)

        # Variables declaration which will contains all the stats needed for the dashboard
        general_stats={}
        activity_list=[]
        stats_dict={}
        labels=[]

        # Generate a field with the user list
        dashboard_graph_form = DashboardGraphForm(user_list=g.user)
        
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
        general_stats["movies"] = Show.query.count()

        # Generate datas for the bar graph
        cur_year=datetime.now().strftime("%Y")
        
        # Set month in French
        locale.setlocale(locale.LC_ALL, "fr_FR.UTF-8")
        for cur_month in range(1,13,1):
                labels.append(datetime.strptime(str(cur_month), "%m").strftime("%B"))

        # Go back to default locale
        locale.setlocale(locale.LC_ALL,locale.getdefaultlocale())
        
        return render_template('show_dashboard.html', activity_list=activity_dict["list"], general_stats=general_stats,labels=labels,cur_year=cur_year,stats_dict=stats_dict,dashboard_graph_form=dashboard_graph_form)

@app.route('/activity/show')
@login_required
@guest_control
def show_activity_flow():
        return render_template('show_activity_flow.html')

@app.route('/activity/update', methods=['POST'])
@login_required
@guest_control
def update_activity_flow():
        
        # Local variables for handling the datatable
        args = json.loads(request.values.get("args"))
        columns = args.get("columns")
        start = args.get('start')
        length = args.get('length')
        draw = args.get('draw')

        # Set default value to 20 for length
        # if pagination is not enabled (Like in dashboard)
        if length == -1:
                length = 20

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
                        entry_text="Le film <a href=\"" +  url_for('show_movie', show_id=cur_activity["object"].id) + "\">" + cur_activity["object"].name + u"</a> vient d'être ajouté par " + user

                elif cur_activity["entry_type"] == "marks":
                        entry_type="<a class=\"disabled btn btn-primary btn-xs\">Note</a>"      

                        # Sometimes, the comment can be Null (Especially after an import
                        # So, we need to put a default user in order to avoid a NoneType Exception
                        if cur_activity["object"].comment == None:
                                comment=""
                        else:
                                comment=cur_activity["object"].comment.replace('"','\'')

                        # Precise if this is a mark for an homework or a simple mark
                        if cur_activity["object"].updated_when != None and cur_activity["object"].homework_when != None:

                                entry_type+=" <a class=\"disabled btn btn-warning btn-xs\">Devoir</a>"  

                                # Define the text that will be shown on the datatable
                                entry_text=cur_activity["object"].user.nickname + u" vient de remplir son devoir sur le film <a href=\"" + url_for('show_movie', show_id=cur_activity["object"].show_id) +"\">" +  cur_activity["object"].movie.name + "</a> .La note est de <span title=\"Commentaire\" data-html=\"true\" data-toggle=\"popover\" data-placement=\"top\" data-trigger=\"hover\" data-content=\"" + comment + "\"><strong>" + str(cur_activity["object"].mark) +"</strong></span>"

                        else:
                                # Define the text that will be shown on the datatable
                                entry_text=cur_activity["object"].user.nickname + u" a noté le film <a href=\"" + url_for('show_movie', show_id=cur_activity["object"].show_id) +"\">" +  cur_activity["object"].movie.name + "</a> avec la note <span title=\"Commentaire\" data-toggle=\"popover\" data-placement=\"top\" data-html=\"true\" data-trigger=\"hover\" data-content=\"" + comment + "\"><strong>" + str(cur_activity["object"].mark) +"</strong></span>"

                elif cur_activity["entry_type"] == "homeworks":
                        entry_type="<a class=\"disabled btn btn-warning btn-xs\">Devoir</a>"

                        # Define the text that will be shown on the datatable
                        entry_text=cur_activity["object"].homework_who_user.nickname + " vient de donner <a href=\"" + url_for('show_movie', show_id=cur_activity["object"].show_id) + "\">" +  cur_activity["object"].movie.name + "</a> en devoir a " + cur_activity["object"].user.nickname

                elif cur_activity["entry_type"] == "comments":
                        entry_type="<a class=\"disabled btn btn-comment btn-xs\">Commentaire</a>"

                        # Check that the mark comment is not empty in order to avoid an exception
                        # when encoding the string
                        if cur_activity["object"].mark.comment == None:
                                cur_activity["object"].mark.comment = "N/A"

                        # Define the text that will be shown on the datatable
                        entry_text=cur_activity["object"].user.nickname + " vient de poster un <span title=\"Commentaire\" data-toggle=\"popover\" data-placement=\"top\" data-trigger=\"hover\" data-content=\"" + cur_activity["object"].message + "\"><strong>commentaire</strong></span> sur le film <a href=\"" + url_for('show_movie', show_id=cur_activity["object"].mark.movie.id) + "\">" +  cur_activity["object"].mark.movie.name + "</a> en réponse à <strong><span title=\"Commentaire\" data-toggle=\"popover\" data-placement=\"top\" data-html=\"true\" data-trigger=\"hover\" data-html=\"true\" data-content=\"" + cur_activity["object"].mark.comment + "\">" + cur_activity["object"].mark.user.nickname + "</strong></span>"

                elif cur_activity["entry_type"] == "favorites":
                        entry_type="<a class=\"disabled btn btn-favorite btn-xs\">Favori</a>"

                        # Define the text that will be shown on the datatable
                        entry_text=cur_activity["object"].user.nickname + " vient d'ajouter en favori <a href=\"" + url_for('show_movie', show_id=cur_activity["object"].show_id) + "\">" +  cur_activity["object"].movie.name + "</a> - Niveau <i class=\"fa fa-star " + cur_activity["object"].star_type + "\"</i>"

                # Append the processed entry to the dictionnary that will be used by the datatable
                activity_dict["data"].append({"entry_type" : entry_type, "entry_text" : entry_text })

        # Return the dictionnary as a JSON object
        return json.dumps(activity_dict)

@app.route('/json/graph_by_year', methods=['POST'])
@login_required
@guest_control
def graph_movies_by_year():
        
        # Fetch the year in the post data
        year=request.form.get("year")
        user=request.form.get("user")

        # Create data dictionary containing movies seen for the logged user
        # in theaters and in others places
        data={"theaters": [], "others": []}

        # Fill the dictionnary for each month
        for cur_month in range(1,13,1):

                data["theaters"].append(Mark.query.filter(Mark.mark!=None,Mark.user_id==user,Mark.user_id==user,Mark.seen_where=="C",db.func.month(Mark.seen_when)==cur_month,db.func.year(Mark.seen_when)==year).count())
                data["others"].append(Mark.query.filter(Mark.mark!=None,Mark.user_id==user,Mark.user_id==user,Mark.seen_where=="M",db.func.month(Mark.seen_when)==cur_month,db.func.year(Mark.seen_when)==year).count())
        
        # Send the dictionnary to the client side
        return json.dumps(data)
