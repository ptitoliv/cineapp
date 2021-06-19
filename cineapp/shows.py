# -*- coding: utf-8 -*-

from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
from builtins import next
from builtins import str
from builtins import range
import urllib.request, urllib.parse, urllib.error, hashlib, re, os, locale, json, copy, time,html2text
from datetime import datetime
from flask import render_template, flash, redirect, url_for, g, request, session, abort, Blueprint
from flask_login import login_user, logout_user, current_user, login_required
from flask_wtf import Form
from wtforms.ext.sqlalchemy.orm import model_form
from wtforms.ext.sqlalchemy.fields import QuerySelectField
from cineapp import app, db, lm
from cineapp.forms import LoginForm, AddUserForm, AddShowForm, MarkShowForm, SearchShowForm, SelectShowForm, ConfirmShowForm, FilterForm, UserForm, PasswordForm, HomeworkForm, UpdateShowForm, DashboardGraphForm
from cineapp.models import User, Show, Mark, Origin, Type, FavoriteShow, FavoriteType, PushNotification, Movie, TVShow, ProductionStatus
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

show_bp = Blueprint('show',__name__,url_prefix='/<show_type>')

@show_bp.url_value_preprocessor
def check_show_type(endpoint,values):
    show_type = values.pop('show_type')

    # Check if the URL is allowed or not
    if show_type not in [ "movies", "tvshows" ]:
        abort(404)
    else:
        session["show_type"]=show_type
        g.show_type=show_type


@show_bp.route('/add', methods=['GET','POST'])
@login_required
@guest_control
def add_show():

        # First, generate all the forms that we going to use in the view
        search_form=SearchShowForm() 

        # Render the template
        return render_template('add_show_wizard.html', search_form=search_form, header_text=g.messages["label_add"], endpoint="add")

@show_bp.route('/add/select/<int:page>', methods=['GET','POST'], endpoint="select_add_show")
@show_bp.route('/add/select', methods=['POST'], endpoint="select_add_show")
@show_bp.route('/update/select/<int:page>', methods=['GET','POST'], endpoint="select_update_show")
@show_bp.route('/update/select', methods=['POST'], endpoint="select_update_show")
@login_required
@guest_control
def select_show(page=1):

        """
                This functions fetch shows from the API using pagination system in order to avoid a timeout with the API
                and also a too long time execution due to an high shows number to fetch and display
        """

        # Calculate endpoint
        endpoint=request.endpoint.split("_")[1]

        # Create a search form in order to get the search query from the search wizard step
        search_form=SearchShowForm()

        # If we come from the search_show for, put the query string into a session
        if search_form.search.data != None and search_form.search.data != "":
                query_show=search_form.search.data
                session['query_show'] = search_form.search.data
        else:
                query_show=session.get('query_show',None)

        # Check if we correctly do a search, if not => Let's go back to the add show form
        if search_form.submit_search.data and not search_form.validate_on_submit():
                flash('Veuillez saisir une recherche !', 'warning')
                
                if endpoint == "add":
                        header_text=u"%s" % g.messages["label_add"]
                elif endpoint == "update":
                        show = session.get("show")
                        header_text=u"%s %s" % (g.messages["label_update"], show.name)

                return render_template('add_show_wizard.html', search_form=search_form, header_text=header_text,endpoint=endpoint)

        # If we are here and that there is nothing into query_string => There is an issue
        # Let's go back to the main form
        if query_show == None:
                flash("Absence de chaine de recherche", 'danger')
                return redirect(url_for('add_show'))

        # Fetch how many pages we have to handle
        total_pages = search_page_number(query_show,show_type=g.show_type)

        # Check if the page number is correct
        if page < 1 or page > total_pages:
                flash("Page de resultat inexistante", 'danger')
                return redirect(url_for('show.add_show',show_type=g.show_type))

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
        shows_list=search_shows(query_show,g.show_type,page)
        select_form=SelectShowForm(g.show_type,shows_list)
        session["page"] = page

        # Put the current shows_list into the session
        # We'll need it to fill the form in the next wizard step
        session["shows_list"] = shows_list

        # Check if we have some results, if not tell the user that there is no matching results
        # and propose it to make a new search
        if total_pages == 1 and len(select_form.show.choices) == 0:
                flash("Aucun résultat pour cette recherche", "warning")
                return redirect(url_for("show.add_show",show_type=g.show_type))

        return render_template('select_show_wizard.html', select_form=select_form, cur_page=page, total_pages=total_pages, has_prev=has_prev, has_next=has_next,endpoint=endpoint)


@show_bp.route('/add/confirm', methods=['POST'], endpoint="confirm_add_show")
@show_bp.route('/update/confirm', methods=['POST'], endpoint="confirm_update_show")
@login_required
@guest_control
def confirm_show():

        # Calculate endpoint
        endpoint=request.endpoint.split("_")[1]

        # Create the select form for validation
        select_form=SelectShowForm(g.show_type)

        # Validate selection form
        if select_form.submit_select.data:

                # Fetch the query from the previous form in order to fill correctly the radio choices
                select_form=SelectShowForm(g.show_type,session.get("shows_list",None))

                # If we are here, we displayed the form once and we want to go to the wizard next step doing a form validation
                if select_form.validate_on_submit():
                
                        # Last step : Set type and origin and add the show
                        # Note : Show_id is the TMVDB id
                        show_form_tmvdb=get_show(select_form.show.data, True, show_type=g.show_type)

                        if endpoint == "add":

                                # Generate the confirmation form with the correct value
                                confirm_form=ConfirmShowForm(button_label=g.messages["label_generic"])
                                confirm_form.show_id.data=select_form.show.data

                        elif endpoint == "update":
                                
                                # Get the show object in order to get origin and type
                                show_id=session.get('show_id',None)

                                if show_id == None:
                                        flash("Erreur générale","danger")
                                        return redirect(url_for("list_shows"))

                                # If we are here, we have a usable show_id value => Let's fetch the show object
                                # and use the type and origin value for filling confirm_form.
                                show_to_update=Show.query.get(show_id)
                                confirm_form=ConfirmShowForm(button_label=g.messages["label_generic"],origin=show_to_update.origin_object,type=show_to_update.type_object)

                                # And then update the others fields
                                confirm_form.show_id.data=select_form.show.data

                                if g.show_type=="movies":
                                    confirm_form.submit_confirm.label.text="Mettre à jour le film"
                                elif g.show_type=="tvshows":
                                    confirm_form.submit_confirm.label.text="Mettre à jour la série"

                        # Since the production_status object is not available because the object is not commited
                        # let's generate a temporary standalone object filled using the string got in tmvdb
                        if g.show_type == "tvshows":
                            production_status=ProductionStatus.query.get(show_form_tmvdb.production_status)
                        else:
                            production_status=None

                        # Go to the final confirmation form
                        return render_template('confirm_show_wizard.html', show=show_form_tmvdb, production_status=production_status, form=confirm_form, endpoint=endpoint)
                else:
                        # Warn the user that the form is incomplete
                        if endpoint == "add":
                                return redirect(url_for('show.select_add_show',show_type=g.show_type,page=session["page"]))
                        elif endpoint == "update":
                                return redirect(url_for('show.select_update_show',show_type=g.show_type,page=session["page"]))

        # Create the form we're going to use    
        confirm_form=ConfirmShowForm(button_label=g.messages["label_generic"])

        # Confirmation form => add into the database
        if confirm_form.submit_confirm.data and confirm_form.validate_on_submit():

                if endpoint == "add":

                        # Form is okay => We can add the show
                        show_to_create=get_show(confirm_form.show_id.data,show_type=g.show_type)
                        show_to_create.added_by_user=g.user.id
                        show_to_create.type=confirm_form.type.data.id
                        show_to_create.origin=confirm_form.origin.data.id
                        show_to_create.added_when=datetime.now()

                        # Add the show in the database
                        try:

                                # Check if the poster has been correctly downloaded
                                if show_to_create.poster_path:
                                        flash('Affiche téléchargée','success')
                                else:
                                        flash('Impossible de télécharger le poster','warning')

                                db.session.add(show_to_create)
                                db.session.flush()
                                new_show_id=show_to_create.id
                                db.session.commit()

                                flash(g.messages["flash_add_success"],'success')

                                # Show has been added => Send notifications
                                add_show_notification(show_to_create)
                                
                                # Show added ==> Go to the mark form !
                                return redirect(url_for('show.mark_show',show_type=g.show_type,show_id_form=new_show_id))

                        except IntegrityError as e:
                                app.logger.error('Impossible d\'ajouter le show: %s' % e)
                                flash(g.messages["flash_already_exists"],'danger')
                                db.session.rollback()
                                return redirect(url_for('show.add_show',show_type=g.show_type))

                elif endpoint == "update":
        
                        # Form is okay => Fetch the show and update it
                        show_id=session.get('show_id',None)

                        if show_id == None:
                                flash("Erreur générale","danger")
                                return redirect(url_for("list_shows"))
                        
                        # If we are here, we have a usable show_id value
                        show=Show.query.get(show_id)

                        # If the show_id is an incorrect value => Go back to the show list
                        # Don't go back to the show file page since the show_id is an incorrect value
                        if show == None:
                                flash("Erreur générale","danger")
                                return redirect(url_for("shows_list"))

                        # All checks are okay => Update the show !
                        temp_show=get_show(confirm_form.show_id.data)

                        # Put the notifications into a dictionnary for notification mail
                        notification_data={}
                        notification_data["old"]={ "name": show.name,
                                        "original_name": show.original_name,
                                        "release_date" : show.release_date,
                                        "director" : show.director,
                                        "type" : show.type_object.type,
                                        "origin" : show.origin_object.origin,
                                        "overview": show.overview
                                        }

                        # Update the object that will be stored in the database
                        show.name=temp_show.name
                        show.original_name=temp_show.original_name
                        show.release_date=temp_show.release_date
                        show.url=temp_show.url
                        show.tmvdb_id=temp_show.tmvdb_id
                        show.director=temp_show.director
                        show.overview=temp_show.overview
                        show.poster_path=temp_show.poster_path
                        show.type=confirm_form.type.data.id
                        show.origin=confirm_form.origin.data.id

                        # Let's consider specific fields considering show_type
                        if type(show) is Movie:
                            notification_data["old"]["duration"]=show.duration
                            show.duration=temp_show.duration
                        elif type(show) is TVShow:
                            notification_data["old"]["nb_seasons"]=show.nb_seasons
                            notification_data["old"]["production_status"]=show.production_status_obj.translated_status
                            show.production_status=temp_show.production_status

                        # Add the show in the database
                        try:
                                db.session.add(show)
                                db.session.flush()
                                db.session.commit()

                                flash(g.messages["flash_update_success"],'success')

                                # Check if the poster has been correctly downloaded
                                if show.poster_path:
                                        flash('Affiche téléchargée','success')
                                else:
                                        flash('Impossible de télécharger le poster','warning')
                                
                                # Update the dictionnary with the update show data
                                notification_data["new"]={ "name": show.name,
                                        "original_name": show.original_name,
                                        "release_date" : show.release_date,
                                        "director" : show.director,
                                        "type" : show.type_object.type,
                                        "origin" : show.origin_object.origin,
                                        "id" : show.id,
                                        "overview": show.overview
                                        }

                                # Let's consider specific fields considering show_type
                                if type(show) is Movie:
                                    notification_data["new"]["duration"]=show.duration
                                elif type(show) is TVShow:
                                    notification_data["new"]["nb_seasons"]=show.nb_seasons
                                    notification_data["new"]["production_status"]=show.production_status_obj.translated_status

                                # Show has been updated => Send notifications
                                update_show_notification(notification_data)

                                # Clear the session variables
                                session.pop('show')
                                session.pop('show_id')
                                session.pop('query_show')
                                
                                # Show updated ==> Go to the show page !
                                return redirect(url_for('show.display_show',show_type=g.show_type,show_id=show.id))

                        except IntegrityError as e:
                                if g.show_type=="movies":
                                    flash('Film déjà existant','danger')
                                elif g.show_type=="tvshows":
                                    flash('Série déjà existante','danger')
                                db.session.rollback()
                                return redirect(url_for('display_show.html',show_id=show.id))

        # If no validation form is filled, go back to the wizard first step
        return redirect(url_for('show.add_show',show_type=g.show_type)) 


@show_bp.route('/update',methods=['POST'])
@login_required
@guest_control
def update_show():

        # Generate the list with the choices returned via the API
        update_show_form=UpdateShowForm(g.messages["label_generic"])
        search_form=SearchShowForm() 
        select_form=SelectShowForm(g.show_type)
        confirm_form=ConfirmShowForm()

        # We come from the show page 
        if update_show_form.submit_update_show.data and update_show_form.validate_on_submit():

                # In stead of getting the query string, directly use the show title from the database          
                show=Show.query.get_or_404(update_show_form.show_id.data)
                search_form.search.data=show.name

                # Put into a session variable the show id we want to update in order to do the final update on the last wizard step
                session['show_id'] = show.id

                # Put the object into the session array => We'll need it later
                session['show']=show
                return render_template('add_show_wizard.html', search_form=search_form,header_text=u"%s %s" % (g.messages["label_update"],show.name), endpoint="update")

        else:

            # If the form is not validated, we shouldn't be there ==> Let's go to the index
            flash("Erreur Générale", "danger")
            return(url_for('index'))

@show_bp.route('/show/<int:show_id>')
@login_required
def display_show(show_id):

        # Select show
        if g.show_type == "movies":
            show = Movie.query.get_or_404(show_id)
        elif g.show_type == "tvshows":
            show = TVShow.query.get_or_404(show_id)
        else:
            abort(404)

        # Initialize the dict which will contain the data to be displayed
        mark_users=[]

        # Get user list
        users=User.query.all()

        # Init the form that will be used if we want to update the show data
        update_show_form=UpdateShowForm(g.messages["label_generic"],show_id)

        # Browse all users
        for cur_user in users:
                
                # Let's check if the show has already been marked by the user
                marked_show=Mark.query.get((cur_user.id,show_id))

                if marked_show != None:

                        # Replace the seen_where letter by a nicer text
                        if marked_show.seen_where=="C":
                                seen_where_text="Cinema"
                        elif marked_show.seen_where=="M":
                                seen_where_text="Maison"

                        # We are in homework mode if a user gave an homework AND the mark is still none
                        # If not we are in mark mode
                        if marked_show.homework_who != None and marked_show.mark == None:
                                mark_users.append({ "user": cur_user, "mark": "homework_in_progress", "seen_where": None, "seen_when": None, "comment": None, "homework_who": marked_show.homework_who_user, "mark_comments": marked_show.active_comments })
                        else:
                                mark_users.append({ "user": cur_user, "mark": marked_show.mark, "seen_where": seen_where_text, "seen_when": marked_show.seen_when.strftime("%d/%m/%Y") ,"comment": marked_show.comment, "homework_who": marked_show.homework_who_user, "mark_comments": marked_show.active_comments })
                else:
                        mark_users.append({ "user" : cur_user, "mark": None, "seen_where": None, "seen_when": None, "comment": None })

        # Let's check if the show has already been marked by the user
        marked_show=Mark.query.get((g.user.id,show_id))

        # Get the favorite types list
        favorite_type_list = FavoriteType.query.all()

        if marked_show is None or marked_show.mark == None:
                return render_template('display_show.html', show=show, mark_users=mark_users, show_next=next(show),show_prev=show.prev(),marked_flag=False,update_show_form=update_show_form,favorite_type_list=favorite_type_list)
        else:
                return render_template('display_show.html', show=show, mark_users=mark_users, show_next=next(show),show_prev=show.prev(),marked_flag=True, update_show_form=update_show_form,favorite_type_list=favorite_type_list)

@show_bp.route('/list')
@app.route('/reset', endpoint="reset_list")
@app.route('/filter', methods=[ 'GET', 'POST' ], endpoint="filter_form")
@login_required
def list_shows():

        # Display the search form
        filter_form = FilterForm()

        # Fetch the query string or dict => We'll need it later
        session_query=session.get('query',None)
        
        # By default, don't clean the ,show_id=show_iddatatable state
        clear_table=False

        # If we catch the reset_list endpoint, well reset the list in initial state
        if request.endpoint == "reset_list":

                # Reset all the values in order to have the initial list
                session.pop('query',None)

                # Tell that we must reset the table on next load
                session['clear_table_on_next_reload']=True

                # And go back to the list
                return redirect(url_for("show.list_shows",show_type=g.show_type))

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

                if filter_form.origin.data == None and filter_form.type.data == None and filter_form.where.data == None and filter_form.favorite.data == None:
                        # All filter are empty => Let's display the list
                        session['search_type']="list"
                else:

                        # Put the forms parameter into a session object in order to be handled by the datatable
                        session['search_type']="filter_origin_type"
                        filter_dict = {'origin' : None, 'type': None, 'seen_where' : None, 'favorite': None}

                        if filter_form.origin.data != None:
                                filter_dict['origin'] = filter_form.origin.data.id

                        if filter_form.type.data != None:
                                filter_dict['type'] = filter_form.type.data.id

                        if filter_form.where.data != None:

                                # Use that field only if we are in movies mode
                                # In other mode, we are necessarily at home
                                if g.show_type=="movies":
                                    filter_dict['seen_where'] = filter_form.where.data.id

                        if filter_form.favorite.data != None:
                                filter_dict['favorite'] = filter_form.favorite.data.id

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

                if session_query['favorite'] == None:
                        favorite=None
                else:
                        favorite=User.query.get(session_query['favorite'])

                # Recreate the form with the set default values
                filter_form=FilterForm(origin=origin,type=type,where=seen_where)

        else:
                # We are in list mode, check if we must clear the table after a reset
                session['search_type']="list"
                clear_table=session.pop('clear_table_on_next_reload',None)

        # Let's fetch all the users, I will need them
        users = User.query.all()
        return render_template('list_shows.html', users=users,filter_form=filter_form,clear_table=clear_table)


@show_bp.route('/mark/<int:show_id_form>', methods=['GET','POST'])
@login_required
@guest_control
def mark_show(show_id_form):
        # Select show
        form=MarkShowForm(button_label=g.messages["label_generic_possessive"])

        # Select show
        if g.show_type == "movies":
            show = Movie.query.get_or_404(show_id_form)
        elif g.show_type == "tvshows":
            show = TVShow.query.get_or_404(show_id_form)
        else:
            abort(404)

        # Let's check if the show has already been marked
        marked_show=Mark.query.get((g.user.id,show_id_form))

        # Test if the form has been submitted
        if form.submit_mark.data or form.submit_mark_slack.data or form.submit_mark_only.data:

                # Mark the show and display the correct page
                if form.validate_on_submit():

                        if marked_show == None:
                                # The show has never been marked => Create the object
                                marked_show=Mark(user_id=g.user.id,
                                        show_id=show.id,
                                        seen_when=form.seen_when.data,
                                        seen_where=form.seen_where.data,
                                        mark=form.mark.data,
                                        comment=form.comment.data,
                                        updated_when=datetime.now()
                                )       
                
                                flash_message_success="Note ajoutée"
                                notif_type="add"
                        else:
                                # Update Show
                                marked_show.mark=form.mark.data
                                marked_show.comment=form.comment.data
                                marked_show.seen_when=form.seen_when.data
                                marked_show.seen_where=form.seen_where.data

                                # If we mark an homework, let's set the date in order to be on the activity flow
                                # Rating an homework mean there is an homework date but not a mark date
                                if marked_show.updated_when == None and marked_show.homework_when != None:
                                        marked_show.updated_when=datetime.now()
                                        flash_message_success="Devoir rempli"
                                        notif_type="homework"
                                else:
                                        flash_message_success="Note mise à jour"
                                        notif_type="update"
                        try:
                                db.session.add(marked_show)
                                db.session.commit()
                                flash(flash_message_success,'success')

                                # Let's display some debug for notifications
                                app.logger.debug("Notifications de l'utilisateur : %s", g.user.notifications)
                                app.logger.debug("Envoi des notifications SLACK %s", form.submit_mark_slack.data)

                                # Send notification
                                if mark_show_notification(marked_show,notif_type) == 0:
                                        flash('Note envoyée par mail','success')
                                else:
                                        flash('Impossible d\'envoyer la note par mail','danger')

                                # Send Slack Notification if needed
                                if g.user.notifications["notif_slack"] and form.submit_mark_slack.data:
                                        slack_result = slack_mark_notification(marked_show,app,g.show_type)
                                        if slack_result == 0:
                                                flash('Note envoyée sur Slack','success')
                                        elif slack_result == -1:
                                                flash('Notifications Slack désactivées','warning')
                                        else:
                                                flash('Impossible d\'envoyer la note sur Slack','danger')

                                return redirect(url_for('show.display_show',show_type=g.show_type,show_id=show_id_form))
                                
                        except IntegrityError:
                                db.session.rollback()
                                flash('Impossible de noter le film','danger')
                                return render_template('display_show.html', show=show, mark=True, marked_flag=False, form=form)

                        except FlushError:
                                db.session.rollback()
                                flash('Impossible de noter le film','danger')
                                return render_template('display_show.html', show=show, mark=True, marked_flag=False, form=form)
                
                else:
                        return render_template('display_show.html', show=show, mark=True, marked_flag=False, form=form)

        if marked_show is None or marked_show.mark == None:
                return render_template('display_show.html', show=show, mark=True, marked_flag=False, form=form)
        else:
                # Show has already been marked => Fill the form with data
                form=MarkShowForm(button_label=g.messages["label_generic_possessive"],mark=marked_show.mark,comment=marked_show.comment,seen_when=marked_show.seen_when,seen_where=marked_show.seen_where)
                return render_template('display_show.html', show=show, mark=True, marked_flag=True,form=form)


@show_bp.route('/json', methods=['GET','POST'])
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

                # Let's build msearch base query
                if g.show_type=="movies":
                    basequery = Movie.query
                elif g.show_type=="tvshows":
                    basequery = TVShow.query

                # Let's build the filtered requested following what has been posted in the filter form
                filter_fields=session.get('query')

                # If we must sort by favorite, the query is not the same. Let's generate here   
                if filter_field == FavoriteType.star_weight:

                        # We only want shows with favorite defined for the concerned user
                        shows_query = basequery.outerjoin(Mark).outerjoin(FavoriteShow).filter(FavoriteShow.user_id==filter_user).outerjoin(FavoriteType)
                else:
                        # All the others sorts refer to the Mark.user_id column
                        shows_query = basequery.outerjoin(Mark).outerjoin(FavoriteShow).filter(Mark.user_id==filter_user).outerjoin(FavoriteType)

                # Check that we have a real list in order to avoid an exception 
                if isinstance(filter_fields,dict):
                        if filter_fields['origin'] != None:
                                shows_query = shows_query.filter(Show.origin==filter_fields['origin'])

                        if filter_fields['type'] != None:
                                shows_query = shows_query.filter(Show.type==filter_fields['type'])

                        if filter_fields['seen_where'] != None:

                                # We want to sort shows for a specific user keeping the seen_where filter enabled
                                # So we want to see shows seen in theater (or not) by a user sorting these shows by marks of another user
                                # Since we sort by marks, we don't want to see shows without a mark for that user
                                # So we need that to build that specific subquery.

                                # First let's fetch the shows seen by a user in theaters
                                shows_seen_in_theater = Mark.query.filter(Mark.user_id==filter_fields['seen_where']).filter(Mark.seen_where=='C').all()
                                array_shows_seen_in_theater = []

                                # Then build a list of these shows
                                for cur_show_seen_in_theater in shows_seen_in_theater:
                                        array_shows_seen_in_theater.append(cur_show_seen_in_theater.show_id)
                                
                                # Finally let's build the filter that will be used later building the query
                                shows_query = shows_query.filter(Mark.show_id.in_(array_shows_seen_in_theater))

                        if filter_fields['favorite'] !=None:

                                # Same behaviour than the previous one
                                favorite_shows = FavoriteShow.query.filter(FavoriteShow.user_id == filter_fields['favorite']).all()
                                favorite_shows_array = []

                                for cur_favorite_show in favorite_shows:
                                        favorite_shows_array.append(cur_favorite_show.show_id)

                                shows_query = shows_query.filter(FavoriteShow.show_id.in_(favorite_shows_array))

                # Sort my desc marks
                if order_dir == "desc":
                        if session.get('search_type') == 'list': 
                                shows = shows_query.filter(filter_field != None).order_by(desc(filter_field)).slice(int(start),int(start) + int(length))
                                count_shows=shows_query.count()

                        elif session.get('search_type') == 'filter_origin_type':
                                shows = shows_query.filter(filter_field != None).order_by(desc(filter_field)).slice(int(start),int(start) + int(length))
                                count_shows=shows_query.filter(Mark.mark != None).count()
                                        
                        elif session.get('search_type') == 'filter':
                                shows = shows_query.msearch(session.get('query'),fields=["name","original_name","director"]).filter(filter_field != None).order_by(desc(filter_field)).slice(int(start),int(start) + int(length))
                                count_shows=shows_query.msearch(session.get('query'),fields=["name","original_name","director"]).filter(filter_field != None).count()

                # Sort by asc marks
                else:
                        if session.get('search_type') == 'list': 
                                shows = shows_query.filter(filter_field != None).order_by(filter_field).slice(int(start),int(start) + int(length))
                                count_shows=shows_query.count()
                        elif session.get('search_type') == 'filter_origin_type':
                                shows = shows_query.filter(filter_field != None).order_by(filter_field).slice(int(start),int(start) + int(length))
                                count_shows=shows_query.filter(filter_field != None).count()
                        elif session.get('search_type') == 'filter':
                                shows = shows_query.msearch(session.get('query'),fields=["name","original_name","director"]).filter(filter_field != None).order_by(filter_field).slice(int(start),int(start) + int(length))
                                count_shows=shows_query.msearch(session.get('query'),fields=["name","original_name","director"]).count()
        else:

                app.logger.info('Entering filter_user is Null')

                # If we are here => No sort by user but only global sort or no sort
                if session.get('search_type') == 'list': 
                        app.logger.info('Entering list search_type')
                        if order_column == "average":
                                if order_dir == "desc":
                                        shows=db.session.query(Show).filter(Show.show_type==g.show_type).join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(desc(db.func.avg(Mark.mark))).slice(int(start),int(start) + int(length))
                                else:
                                        shows=db.session.query(Show).filter(Show.show_type==g.show_type).join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).slice(int(start),int(start) + int(length))
                                
                                count_shows=db.session.query(Show).filter(Show.show_type==g.show_type).join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).count()
                        else:

                                shows = Show.query.filter(Show.show_type==g.show_type).order_by(text(order_column,order_dir)).slice(int(start),int(start) + int(length))
                                count_shows=Show.query.filter(Show.show_type==g.show_type).count()

                # Let's use the filter form
                elif session.get('search_type') == 'filter_origin_type':
                        app.logger.info('Entering list filter_origin_type')
                        # Let's build the filtered requested following what has been posted in the filter form
                        filter_fields=session.get('query')
                        shows_query = Show.query.filter(Show.show_type==g.show_type).outerjoin(Mark).outerjoin(FavoriteShow)

                        if filter_fields['origin'] != None:
                                shows_query = shows_query.filter(Show.origin==filter_fields['origin'])

                        if filter_fields['type'] != None:
                                shows_query = shows_query.filter(Show.type==filter_fields['type'])

                        if filter_fields['seen_where'] !=None:
                                shows_query = shows_query.filter(Mark.user_id==filter_fields['seen_where']).filter(Mark.seen_where=='C')

                        if filter_fields['favorite'] !=None:
                                shows_query = shows_query.filter(FavoriteShow.user_id==filter_fields['favorite'])

                        # Build the request
                        if order_column == "average":
                                if order_dir == "desc":
                                        app.logger.info("Requete par moyenne desecendante")
                                        shows=shows_query.group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(desc(db.func.avg(Mark.mark))).slice(int(start),int(start) + int(length)).all()
                                else:
                                        app.logger.info("Requete par moyenne ascendante")
                                        shows=shows_query.group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).slice(int(start),int(start) + int(length)).all()
                        else:
                                shows = shows_query.order_by(text(order_column,order_dir)).slice(int(start),int(start) + int(length))

                        count_shows=shows_query.count()

                # Here, this is for the string search (Show or director)
                elif session.get('search_type') == 'filter':
                        app.logger.info('Entering list filter')

                        # Let's build msearch base query
                        if g.show_type=="movies":
                            basequery = Movie.query.msearch(session.get('query'),fields=["name","original_name","director"])
                        elif g.show_type=="tvshows":
                            basequery = TVShow.query.msearch(session.get('query'),fields=["name","original_name","director"])

                        if order_column == "average":
                                if order_dir == "desc":
                                        shows=basequery.join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(desc(db.func.avg(Mark.mark))).slice(int(start),int(start) + int(length)).all()
                                else:
                                        shows=basequery.join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).slice(int(start),int(start) + int(length)).all()

                                count_shows=basequery.join(Mark).group_by(Mark.show_id).having(db.func.avg(Mark.mark!=None)).order_by(db.func.avg(Mark.mark)).count()
                        else:
                                shows = basequery.order_by(text(order_column,order_dir)).slice(int(start),int(start) + int(length))
                                count_shows=basequery.count()

        # Let's fetch all the users, I will need them
        users = User.query.all()

        # Init the dictionnary
        dict_show = { "draw": draw , "recordsTotal": count_shows, "recordsFiltered" : count_shows, "data": []}
        for cur_show in shows:
                # Fetch the note for the logged user
                my_mark=None
                my_when="-"
                my_where=""
                my_comment=""
                my_fav=None

                # Calculate the average mark for each show
                average_mark_query=db.session.query(db.func.avg(Mark.mark).label("average")).filter(Mark.show_id==cur_show.id).one()
                
                try:
                        # Round the average mark for a better display
                        average_mark=round(float(average_mark_query.average),2)
                except:
                        # There is no average because no mark recorded
                        average_mark="-"

                # Get the cur_mark for the user
                for cur_mark in cur_show.marked_by_users:
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

                # Check if the user has set the show as favorite
                tmp_fav = [x for x in cur_show.favorite_users if x.user_id == g.user.id]
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
                        dict_homework[cur_user.id]={ "when" : None, "who:" : None, "link" : url_for("add_homework",show_id=cur_show.id,user_id=cur_user.id)}
                        for cur_mark in cur_show.marked_by_users:
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

                        # Check if the user has set the show as favorite
                        tmp_fav = [x for x in cur_show.favorite_users if x.user_id == cur_user.id]
                        if len(tmp_fav) != 0:
                                dict_favs[cur_user.id]=tmp_fav[0].star_type

                # Create the json object for the datatable
                dict_show["data"].append({"DT_RowData": { "link": url_for('show.display_show',show_type=g.show_type,show_id=cur_show.id), "mark_link": url_for("show.mark_show",show_type=g.show_type,show_id_form=cur_show.id),"homework_link": dict_homework},
                "id": cur_show.id,"name": cur_show.name, 
                "director": cur_show.director,
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
        return json.dumps(dict_show) 

@show_bp.route('/show/random')
@login_required
def display_show_random():
        """
                Function that redirects to a random movie sheet
        """
        # Fetch all the id matching the active show type
        ids_list=db.session.query(Show.id).filter(Show.show_type==g.show_type).all()

        # Check if there is something to query
        if len(ids_list) == 0:
            flash("Impossible d\'efffectuer une recherche aléatoire - Pas de contenu disponible","danger")
            app.logger.error("Liste vide. Pas de recherche aléatoire possible")
            return redirect(url_for('show.list_shows',show_type=g.show_type))

        # Get the random index id
        random_id = randint(0,len(ids_list)-1)

        # Check if the movie exists
        while Show.query.get(ids_list[random_id].id) is None:
                random_id = randint(0,len(ids_list))

        # Redirect to the movie sheet selected randomly
        return redirect(url_for('show.display_show',show_type=g.show_type,show_id=ids_list[random_id].id))

@show_bp.route('/mark/publish/<int:show_id>', methods=['GET'])
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
                if g.user.notifications["notif_slack"]:
                        slack_result = slack_mark_notification(mark,app,g.show_type)
                        if slack_result == 0:
                                flash('Note envoyée sur Slack','success')
                        elif slack_result == -1:
                                flash('Notifications Slack désactivées','warning')
                        else:
                                flash('Impossible d\'envoyer la note sur Slack','danger')
                return redirect(url_for('show.display_show',show_type=g.show_type,show_id=show_id))
