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
from cineapp.models import User, Show, Mark, Origin, Type, FavoriteShow, FavoriteType, PushNotification, Movie, TVShow
from cineapp.tmvdb import search_shows,get_show,download_poster, search_page_number
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
from cineapp.messages import tvshow_messages, movie_messages

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

        # Set mode to movie by default
        if session.get('show_type') == None:
            app.logger.info("Le type de show n'est pas défini dans la session. Configuration à movie par défaut")
            session["show_type"] = "movie"
       
        # Configure g with the value stored in the session
        # TIP: g is only set for the current request and not globally to the session
        # For that: there is ... session
        g.show_type=session["show_type"]

        if g.show_type == "movie":
            g.messages=movie_messages
        elif g.show_type == "tvshow":
            g.messages=tvshow_messages

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
                        return redirect(request.args.get('next') or url_for('show.list_shows',show_type=g.show_type))

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
@login_required
def switch_show_type(show_type):

    # Check if the URL is allowed or not
    if show_type not in [ "movie", "tvshow" ]:
        app.logger.error("Le mode %s n'est pas autorisé" % show_type)
    else:
        app.logger.info("Bascule vers le mode: %s" % show_type)
        session["show_type"]=show_type

    # Reset all the values in order to have the initial list
    session.pop('query',None)

    # Tell that we must reset the table on next load
    session['clear_table_on_next_reload']=True

    # Redirect to the correct authorized page
    if g.user.is_guest == True:
        return redirect(url_for('show.list_shows',show_type=show_type))
    else:
        return redirect(url_for('index'))


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

@app.route('/dashboard')
@login_required
@guest_control
def show_dashboard():

        # Variables declaration which will contains all the stats needed for the dashboard
        general_stats={}
        activity_list=[]
        stats_dict={}
        labels=[]

        # Generate a field with the user list
        dashboard_graph_form = DashboardGraphForm(user_list=g.user)
        
        # Fetch the last 20 last activity records
        activity_dict=get_activity_list(0,20,show_type=g.show_type)

        # Build a dictionnary with the average and shows count (global / only in theaters and only at home) for all users
        # We do a dictionnary instead of a global GROUP BY in order to have all users including the one without any mark
        # and also allow an easy access to a specific user which is nice for the dashboard display
        users=User.query.all()

        for cur_user in users:
                try:
                        # Fetch the user object and the current average
                        avg_query=db.session.query(db.func.avg(Mark.mark).label("average")).join(Show).filter(Show.show_type==g.show_type).filter(Mark.mark!=None,Mark.user_id==cur_user.id).one()
                        stats_dict[cur_user.id]={ "user": cur_user, "avg": round(float(avg_query.average),2), "shows_total" : 0, "shows_theaters" : 0, "shows_home": 0 }

                except TypeError:
                        # If we are here, that means the user doesn't have an average (Maybe because no mark recorded)
                        stats_dict[cur_user.id]={ "user": cur_user, "avg": "N/A",  "shows_total" : 0, "shows_theaters" : 0, "shows_home": 0 }

                # Let's count the shows for each user
                stats_dict[cur_user.id]["shows_total"] = Mark.query.join(Show).filter(Show.show_type==g.show_type).filter(Mark.mark!=None,Mark.user_id==cur_user.id).count()
                stats_dict[cur_user.id]["shows_theaters"] = Mark.query.join(Show).filter(Show.show_type==g.show_type).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Mark.seen_where=="C").count() 
                stats_dict[cur_user.id]["shows_home"] = Mark.query.join(Show).filter(Show.show_type==g.show_type).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Mark.seen_where=="M").count() 

        # Fetch general databases statistics
        general_stats["shows"] = Show.query.filter(Show.show_type==g.show_type).count()

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
        temp_activity_dict=get_activity_list(start,length, g.show_type)

        # Initialize dict which will contains that presented to the datatable
        activity_dict = { "draw": draw , "recordsTotal": temp_activity_dict["count"], "recordsFiltered" : temp_activity_dict["count"], "data": []}

        # Let's fill the activity_dict with data good format for the datatable
        for cur_activity in temp_activity_dict["list"]:
                if cur_activity["entry_type"] == "shows":
                        entry_type="<a class=\"disabled btn btn-danger btn-xs\">Entrée</a>"

                        # Sometimes, the user can be Null (Especially after an import
                        # So, we need to put a default user in order to avoid a NoneType Exception
                        if cur_activity["object"].added_by == None:
                                user="CineBot"
                        else:
                                user=cur_activity["object"].added_by.nickname

                        # Define the text that will be shown on the datatable
                        entry_text=g.messages["label_generic_uppercase"] + " <a href=\"" +  url_for('show.display_show',show_type=g.show_type, show_id=cur_activity["object"].id) + "\">" + cur_activity["object"].name + u"</a> vient d'être " + g.messages["label_text_added"] + " par " + user

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
                                entry_text=cur_activity["object"].user.nickname + u" vient de remplir son devoir sur " + g.messages["label_generic"] + " <a href=\"" + url_for('show.display_show', show_type=g.show_type, show_id=cur_activity["object"].show_id) +"\">" +  cur_activity["object"].show.name + "</a> .La note est de <span title=\"Commentaire\" data-html=\"true\" data-toggle=\"popover\" data-placement=\"top\" data-trigger=\"hover\" data-content=\"" + comment + "\"><strong>" + str(cur_activity["object"].mark) +"</strong></span>"

                        else:
                                # Define the text that will be shown on the datatable
                                entry_text=cur_activity["object"].user.nickname + u" a noté " + g.messages["label_generic"] + " <a href=\"" + url_for('show.display_show', show_type=g.show_type, show_id=cur_activity["object"].show_id) +"\">" +  cur_activity["object"].show.name + "</a> avec la note <span title=\"Commentaire\" data-toggle=\"popover\" data-placement=\"top\" data-html=\"true\" data-trigger=\"hover\" data-content=\"" + comment + "\"><strong>" + str(cur_activity["object"].mark) +"</strong></span>"

                elif cur_activity["entry_type"] == "homeworks":
                        entry_type="<a class=\"disabled btn btn-warning btn-xs\">Devoir</a>"

                        # Define the text that will be shown on the datatable
                        entry_text=cur_activity["object"].homework_who_user.nickname + " vient de donner <a href=\"" + url_for('show.display_show', show_type=g.show_type, show_id=cur_activity["object"].show_id) + "\">" +  cur_activity["object"].show.name + "</a> en devoir a " + cur_activity["object"].user.nickname

                elif cur_activity["entry_type"] == "comments":
                        entry_type="<a class=\"disabled btn btn-comment btn-xs\">Commentaire</a>"

                        # Check that the mark comment is not empty in order to avoid an exception
                        # when encoding the string
                        if cur_activity["object"].mark.comment == None:
                                cur_activity["object"].mark.comment = "N/A"

                        # Define the text that will be shown on the datatable
                        entry_text=cur_activity["object"].user.nickname + " vient de poster un <span title=\"Commentaire\" data-toggle=\"popover\" data-placement=\"top\" data-trigger=\"hover\" data-content=\"" + cur_activity["object"].message + "\"><strong>commentaire</strong></span> sur " + g.messages["label_generic"] + " <a href=\"" + url_for('show.display_show',show_type=g.show_type, show_id=cur_activity["object"].mark.show.id) + "\">" +  cur_activity["object"].mark.show.name + "</a> en réponse à <strong><span title=\"Commentaire\" data-toggle=\"popover\" data-placement=\"top\" data-html=\"true\" data-trigger=\"hover\" data-html=\"true\" data-content=\"" + cur_activity["object"].mark.comment + "\">" + cur_activity["object"].mark.user.nickname + "</strong></span>"

                elif cur_activity["entry_type"] == "favorites":
                        entry_type="<a class=\"disabled btn btn-favorite btn-xs\">Favori</a>"

                        # Define the text that will be shown on the datatable
                        entry_text=cur_activity["object"].user.nickname + " vient d'ajouter en favori <a href=\"" + url_for('show.display_show', show_type=g.show_type,show_id=cur_activity["object"].show_id) + "\">" +  cur_activity["object"].show.name + "</a> - Niveau <i class=\"fa fa-star " + cur_activity["object"].star_type + "\"</i>"

                # Append the processed entry to the dictionnary that will be used by the datatable
                activity_dict["data"].append({"entry_type" : entry_type, "entry_text" : entry_text })

        # Return the dictionnary as a JSON object
        return json.dumps(activity_dict)

@app.route('/json/graph_by_year', methods=['POST'])
@login_required
@guest_control
def graph_shows_by_year():
        
        # Fetch the year in the post data
        year=request.form.get("year")
        user=request.form.get("user")

        # Create data dictionary containing shows seen for the logged user
        # in theaters and in others places
        data={"theaters": [], "others": []}

        # Fill the dictionnary for each month
        for cur_month in range(1,13,1):
                if g.show_type=="movie":
                    data["theaters"].append(Mark.query.join(Show).filter(Show.show_type==g.show_type).filter(Mark.mark!=None,Mark.user_id==user,Mark.user_id==user,Mark.seen_where=="C",db.func.month(Mark.seen_when)==cur_month,db.func.year(Mark.seen_when)==year).count())
                data["others"].append(Mark.query.join(Show).filter(Show.show_type==g.show_type).filter(Mark.mark!=None,Mark.user_id==user,Mark.user_id==user,Mark.seen_where=="M",db.func.month(Mark.seen_when)==cur_month,db.func.year(Mark.seen_when)==year).count())
        
        # Send the dictionnary to the client side
        return json.dumps(data)
