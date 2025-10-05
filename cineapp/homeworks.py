# -*- coding: utf-8 -*-

from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
from builtins import next
from builtins import str
from builtins import range
import urllib.request, urllib.parse, urllib.error, hashlib, re, os, locale, json, copy, time,html2text, traceback
from datetime import datetime
from flask import render_template, flash, redirect, url_for, g, request, session, abort, Blueprint
from flask_login import login_user, logout_user, current_user, login_required
from flask_wtf import Form
from wtforms_sqlalchemy.fields import QuerySelectField
from cineapp import lm
from cineapp.forms import HomeworkForm
from cineapp.models import db, User, Show, Mark, Origin, Type, FavoriteShow, FavoriteType, PushNotification, Movie, TVShow, ProductionStatus
from cineapp.tmvdb import search_shows,get_show,download_poster, search_page_number
from cineapp.emails import add_homework_notification, delete_homework_notification
from cineapp.utils import frange, get_activity_list, resize_avatar
from cineapp.push import notification_unsubscribe
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm.exc import FlushError
from sqlalchemy.orm import make_transient, selectinload
from sqlalchemy import desc, or_, and_, Table, text
from sqlalchemy.sql.expression import select, case, literal
from bcrypt import hashpw, gensalt
from werkzeug.utils import secure_filename
from random import randint
from cineapp.slack import slack_mark_notification
from cineapp.auth import guest_control
from flask import current_app as app

homework_bp = Blueprint('homework',__name__,url_prefix='/homework')

@homework_bp.route('/add/<int:show_id>/<int:user_id>')
@login_required
@guest_control
def add_homework(show_id,user_id):

        # Check if the show has already a mark
        mark=Mark.query.get((user_id,show_id))

        if mark != None:

            # Mark exists ==> No need to give an homework
            flash('Impossible de créer le devoir. Une note existe déjà' , 'warning')

        else:

            # Create the mark object
            mark=Mark(user_id=user_id,show_id=show_id,homework_who=g.user.id,homework_when=datetime.now())
    
            # We want to add an homework => Set a session variable in order to tell to the list_shows table not cleaning the table
            session['clear_table']=False
    
            # Add the object to the database
            try:
                    db.session.add(mark)
                    db.session.commit()
                    flash('Devoir ajouté','success')

                    # Send email notification
                    mail_status = add_homework_notification(mark)
                    if mail_status == 0:
                            flash('Notification envoyée','success')
                    elif mail_status == 1: # pragma: no cover
                            flash('Erreur lors de l\'envoi de la notification','danger')
                    elif mail_status == 2:
                            flash('Aucune notification à envoyer','warning')

            except Exception as e: 
                    flash('Impossible de créer le devoir','danger')

        return redirect(url_for('show.display_show',show_id=show_id,show_type=g.show_type))

@homework_bp.route('/delete/<int:show_id>/<int:user_id>')
@login_required
@guest_control
def delete_homework(show_id,user_id):

        # Check if the homework exists and if the user has the right to delete it
        # We can't delete the homework we didn't propose
        homework=Mark.query.options(selectinload(Mark.user),selectinload(Mark.show),selectinload(Mark.homework_who_user)).get((user_id,show_id))
        
        # Homework doesn't exists => Stop processing
        if homework == None or homework.homework_who == None:
                flash("Ce devoir n'existe pas", "danger")
                return redirect(url_for('homework.list_homeworks'))

        # Is the user allowed to delete the homework
        if homework.homework_who != g.user.id:
                flash("Vous n'avez pas le droit de supprimer ce devoir", "danger")
                return redirect(url_for('show.display_show',show_id=show_id,show_type=g.show_type))

        # Copy the object that will be used for notifications
        db.session.expunge(homework)
        homework_copy=copy.deepcopy(homework)
        make_transient(homework_copy)
        db.session.add(homework)

        # We are here => Check that there is not already a mark
        # We don't delete an homework when there is always a mark
        if homework.mark == None:
                # The user didn't mark the movie so we can delete the record
                try:
                        db.session.delete(homework)
                        db.session.commit()
                        flash("Devoir annulé","success")
                        homework_deleted=True
                except: # pragma: no cover
                        flash("Impossible de supprimer la note","danger")
                        homework_deleted=False
        else:
            flash("Impossible de supprimer le devoir - Une note existe déjà","danger")
            homework_deleted=False
                
        # Send email notification after databases operations
        if homework_deleted == True:
            mail_status = delete_homework_notification(homework_copy)
            if mail_status == 0:
                    flash('Notification envoyée','success')
            elif mail_status == 1: # pragma: no cover
                    flash('Erreur lors de l\'envoi de la notification','danger')
            elif mail_status == 2:
                    flash('Aucune notification à envoyer','warning')

        # When finished => Go back to the movie page
        return redirect(url_for('show.display_show',show_id=show_id,show_type=g.show_type))
                
@homework_bp.route('/list',methods=['GET','POST'])
@login_required
@guest_control
def list_homeworks():

        # Create the form
        homework_filter_form=HomeworkForm(to_user_filter=g.user)

        # Intialize the SQL query
        # We sort the results first by null results in order to show
        # shows we have to rate and them shows which have been rated
        # For this query, we use a case statement
        # http://stackoverflow.com/questions/1347894/order-by-null-first-then-order-by-other-variable
        homework_query = Mark.query.join(Mark.show).filter(Show.show_type==g.show_type).order_by(case((Mark.mark == None, 0),else_=1),Show.name).filter(Mark.homework_who != None)

        # Fetch the homeworks
        if homework_filter_form.validate_on_submit():

                # Build the request considering the used fields
                if homework_filter_form.from_user_filter.data != None:
                        homework_query = homework_query.filter(Mark.homework_who == homework_filter_form.from_user_filter.data.id)

                if homework_filter_form.to_user_filter.data != None:
                        homework_query = homework_query.filter(Mark.user_id == homework_filter_form.to_user_filter.data.id)
                        
                homeworks=homework_query.all()
        else:
                homeworks=homework_query.filter(and_(Mark.user_id == g.user.id)).all()

        return render_template('list_homeworks.html',homework_filter_form=homework_filter_form,homeworks=homeworks)
