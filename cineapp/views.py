# -*- coding: utf-8 -*-

from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
from builtins import next
from builtins import str
from builtins import range
import urllib.request, urllib.parse, urllib.error, hashlib, re, os, json, copy, time,html2text
from datetime import datetime
from flask import Blueprint, render_template, flash, redirect, url_for, g, request, session, abort, current_app as app
from flask_login import login_user, logout_user, current_user, login_required
from flask_wtf import Form
from wtforms_sqlalchemy.fields import QuerySelectField
from cineapp import lm
from cineapp.forms import LoginForm, AddUserForm, AddShowForm, MarkShowForm, SearchShowForm, SelectShowForm, ConfirmShowForm, FilterForm, UserForm, PasswordForm, HomeworkForm, UpdateShowForm, DashboardGraphForm
from cineapp.models import db, User, Show, Mark, Origin, Type, FavoriteShow, FavoriteType, PushNotification, Movie, TVShow, VideoGame
from cineapp.tmvdb import search_shows,get_show,download_poster, search_page_number
from cineapp.emails import add_show_notification, mark_show_notification, add_homework_notification, update_show_notification
from cineapp.utils import frange, get_activity_list, humanize_when, resize_avatar
from cineapp.push import notification_unsubscribe
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm.exc import FlushError
from sqlalchemy import desc, or_, and_, Table, text
from sqlalchemy.sql.expression import select, case, literal
from bcrypt import hashpw, gensalt
from werkzeug.utils import secure_filename
from random import randint, sample, shuffle
from cineapp.slack import slack_mark_notification
from cineapp.auth import guest_control

view_bp = Blueprint('main', __name__)

# Login front-door medley : how many tiles each show type contributes. The
# three types always share the same count — a type short on real posters is
# padded with its placeholder so films / séries / jeux vidéo stay balanced.
LOGIN_MEDLEY_PER_TYPE = 20

@view_bp.route('/')
@view_bp.route('/index')
def index():
        return redirect(url_for('main.login'))

def build_login_medley():
        """ Deck of poster tiles for the login medley : an equal share of the
            catalogue's real posters per show type, each type padded up to
            LOGIN_MEDLEY_PER_TYPE with placeholder tiles ({'poster': None}).

            Only posters whose file actually exists in POSTERS_PATH are kept
            as real tiles — a poster_path with no file on disk would render as
            a placeholder anyway. Real posters are shuffled into the centre of
            the deck and the placeholders split to its two ends, so the
            rotated medley grid keeps real posters in its visible core and
            pushes placeholders into the corners clipped by the rotation. """
        # POSTERS_PATH is created at startup (see create_app), so listdir is safe.
        present = set(os.listdir(app.config['POSTERS_PATH']))

        # Array that will contains real posters
        real_posters = []

        # Array that will contain placeholder filled by the default style
        placeholders = []

        # For each show type, let's fill the arrays considering what we have in the database
        for show_type, model in (('movie', Movie), ('tvshow', TVShow), ('videogame', VideoGame)):
                posters = [row[0] for row in db.session.query(model.poster_path).filter(model.poster_path.isnot(None))]
                posters = [poster for poster in posters if poster in present]
                picked = sample(posters, min(len(posters), LOGIN_MEDLEY_PER_TYPE))
                real_posters += [{'type': show_type, 'poster': poster} for poster in picked]
                placeholders += [{'type': show_type, 'poster': None} for _ in range(LOGIN_MEDLEY_PER_TYPE - len(picked))]
        
        # Let's randomize the display
        shuffle(real_posters)
        shuffle(placeholders)
        half = len(placeholders) // 2
        return placeholders[:half] + real_posters + placeholders[half:]

@view_bp.route('/login', methods=['GET','POST'])
def login():

        # Let's check if we are authenticated => If yes redirect to the index page
        if g.user is not None and g.user.is_authenticated:
                return redirect(url_for('main.show_dashboard'))

        # If we are here, we are not login. Build the form and try the login.
        form = LoginForm()
        if form.validate_on_submit():

                # Let's validate the user
                if form.username.data == "guest" and form.password.data == "guest":
                        user = User(guest=True)
                        # User authenticated => Let's login it
                        login_user(user)
                        return redirect(url_for('show.list_shows',show_type=g.show_type))

                user=User.query.filter_by(nickname=form.username.data).first()
                if user is None:
                        flash("Mauvais utilisateur !",'danger')
                        return redirect(url_for('main.login'))
                else:
                        if hashpw(form.password.data.encode('utf-8'), user.password.encode('utf-8')).decode('utf-8') != user.password:
                                flash("Mot de passe incorrect !",'danger')
                                return redirect(url_for('main.login'))

                        # User authenticated => Let's login it
                        login_user(user)

                        # Let's write user nickname in the session (Will be user for the chat feature)
                        # We need to use a session since g object is not available because before_request is not executed on sockets event
                        session["user"] = user

                        return redirect(url_for('main.show_dashboard'))
                return redirect(url_for('main.index'))
        
        return render_template('login.html', title='Sign In', form=form, medley=build_login_medley())

@view_bp.route('/logout')
def logout():
        logout_user()

        # Purge all the subscriptions objects from the current session
        subscriptions_to_delete=PushNotification.query.filter(PushNotification.session_id==session.sid).all()
        for cur_subscription in subscriptions_to_delete:
                notification_unsubscribe(cur_subscription)

        return redirect(url_for('main.index'))

@view_bp.route('/switch/<show_type>')
@login_required
def switch_show_type(show_type):

    # Check if the URL is allowed or not
    if show_type not in [ "movie", "tvshow", "videogame" ]:
        app.logger.error("Le mode %s n'est pas autorisé" % show_type)
        abort(404)
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
        return redirect(url_for('main.index'))


@lm.user_loader
def load_user(id):
        if id == "-1":
                user = User(guest=True)
                return user
        else:
                return User.query.get(int(id))

@view_bp.route('/users/add', methods=['GET','POST'])
@login_required
@guest_control
def add_user():
        form=AddUserForm()
        if form.validate_on_submit():
                # Form is okay => add the user
                # But salt the password before
                hashed_password=hashpw(form.password.data.encode('utf-8'),gensalt())
        
                # Now add the user into the database    
                user=User(guest=False)
                try:

                        # Fill mandatory fields
                        user.nickname=form.username.data
                        user.password=hashed_password
                        user.email=form.email.data

                        # Add the user to the database
                        db.session.add(user)
                        db.session.commit()
                        flash('Utilisateur ajouté','success')

                except IntegrityError:
                        db.session.rollback()
                        flash('Utilisateur déjà existant','danger')

        return render_template('add_user_form.html', form=form)

@view_bp.route('/dashboard')
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
        
        # Distinct shows with at least one rating — used by the dashboard
        # to display catalogue coverage.
        general_stats["shows_marked"] = db.session.query(db.func.count(db.distinct(Mark.show_id))).join(Show).filter(Show.show_type==g.show_type, Mark.mark != None).scalar() or 0

        # Pick a random show the current user hasn't rated yet
        # ~ ==> NOT
        suggestion = None
        unseen_query = Show.query.filter(
                Show.show_type == g.show_type,
                ~Show.id.in_(db.session.query(Mark.show_id).filter(Mark.user_id == g.user.id, Mark.mark != None))
        )

        # Let's pick a random unrated show if there is one available
        unseen_count = unseen_query.count()
        if unseen_count > 0:
                suggestion = unseen_query.offset(randint(0, unseen_count - 1)).limit(1).first()

        # Latest rated shows — feeds the dashboard's "Dernières notes" grid
        # (one card per mark, with the show poster + the rater).
        latest_marks = Mark.query.join(Show).filter(
                Show.show_type == g.show_type,
                Mark.mark != None
        ).order_by(Mark.updated_when.desc()).limit(10).all()

        # Generate datas for the bar graph
        cur_year=datetime.now().strftime("%Y")

        # Month labels in French (abbreviated: janv., févr., mars…) — the process
        # locale is set at startup (see create_app), so %b is already localized.
        for cur_month in range(1,13,1):
                labels.append(datetime.strptime(str(cur_month), "%m").strftime("%b"))

        return render_template('show_dashboard.html', activity_list=activity_dict["list"], general_stats=general_stats,labels=labels,cur_year=cur_year,stats_dict=stats_dict,dashboard_graph_form=dashboard_graph_form,suggestion=suggestion,latest_marks=latest_marks)

@view_bp.route('/activity/show')
@login_required
@guest_control
def show_activity_flow():
        return render_template('show_activity_flow.html')

@view_bp.route('/activity/update', methods=['POST'])
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

        # Fill activity_dict with structured per-entry data. The route returns
        # unitary objects only — each consumer template renders the final HTML
        # itself via a DataTables columns.render callback.
        for cur_activity in temp_activity_dict["list"]:
                entry = { "action_type" : cur_activity["entry_type"] }

                if cur_activity["entry_type"] == "shows":
                        show = cur_activity["object"]
                        author = show.added_by

                        entry["user"] = {
                                "id": author.id if author else 0,
                                "nickname": author.nickname if author else "CineBot",
                                "theme_color": author.theme_color if author else "#1c1820",
                        }
                        entry["show"] = {
                                "id": show.id,
                                "name": show.name,
                                "url": url_for('show.display_show', show_type=g.show_type, show_id=show.id),
                        }
                        entry["when"] = humanize_when(show.added_when)

                elif cur_activity["entry_type"] == "marks":
                        mark = cur_activity["object"]

                        entry["user"] = { "id": mark.user.id, "nickname": mark.user.nickname, "theme_color": mark.user.theme_color }
                        entry["show"] = {
                                "id": mark.show_id,
                                "name": mark.show.name,
                                "url": url_for('show.display_show', show_type=g.show_type, show_id=mark.show_id),
                        }
                        entry["mark"] = {
                                "value": mark.mark,
                                "comment": "" if mark.comment is None else mark.comment.replace('"', '\''),
                                "is_homework_mark": mark.updated_when is not None and mark.homework_when is not None,
                        }
                        entry["when"] = humanize_when(mark.updated_when)

                elif cur_activity["entry_type"] == "homeworks":
                        m = cur_activity["object"]

                        entry["user"] = { "id": m.homework_who_user.id, "nickname": m.homework_who_user.nickname, "theme_color": m.homework_who_user.theme_color }
                        entry["show"] = {
                                "id": m.show_id,
                                "name": m.show.name,
                                "url": url_for('show.display_show', show_type=g.show_type, show_id=m.show_id),
                        }
                        entry["target_user"] = { "id": m.user.id, "nickname": m.user.nickname, "theme_color": m.user.theme_color }
                        entry["when"] = humanize_when(m.homework_when)

                elif cur_activity["entry_type"] == "comments":
                        com = cur_activity["object"]

                        entry["user"] = { "id": com.user.id, "nickname": com.user.nickname, "theme_color": com.user.theme_color }
                        entry["show"] = {
                                "id": com.mark.show.id,
                                "name": com.mark.show.name,
                                "url": url_for('show.display_show', show_type=g.show_type, show_id=com.mark.show.id),
                        }
                        entry["comment"] = { "message": com.message }
                        entry["parent_mark"] = {
                                "user": { "id": com.mark.user.id, "nickname": com.mark.user.nickname, "theme_color": com.mark.user.theme_color },
                                "comment": "N/A" if com.mark.comment is None else com.mark.comment,
                        }
                        entry["when"] = humanize_when(com.posted_when)

                elif cur_activity["entry_type"] == "favorites":
                        fav = cur_activity["object"]

                        entry["user"] = { "id": fav.user.id, "nickname": fav.user.nickname, "theme_color": fav.user.theme_color }
                        entry["show"] = {
                                "id": fav.show_id,
                                "name": fav.show.name,
                                "url": url_for('show.display_show', show_type=g.show_type, show_id=fav.show_id),
                        }
                        entry["favorite"] = { "star_type": fav.star_type }
                        entry["when"] = humanize_when(fav.added_when)

                activity_dict["data"].append(entry)

        # Return the dictionnary as a JSON object
        return json.dumps(activity_dict)
