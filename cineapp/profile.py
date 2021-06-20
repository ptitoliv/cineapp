# -*- coding: utf-8 -*-

from builtins import next
import urllib.request, urllib.parse, urllib.error, re, locale, json, copy, html2text, hashlib, time, os
from datetime import datetime
from flask import render_template, flash, redirect, url_for, g, request, session, abort, Blueprint
from flask_login import login_user, logout_user, current_user, login_required
from flask_wtf import Form
from cineapp import app, db, lm
from cineapp.forms import UserForm, PasswordForm
from cineapp.models import User
from cineapp.utils import frange, get_activity_list, resize_avatar
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm.exc import FlushError
from sqlalchemy import desc, or_, and_, Table, text
from sqlalchemy.sql.expression import select, case, literal
from bcrypt import hashpw, gensalt
from werkzeug.utils import secure_filename
from random import randint
from cineapp.auth import guest_control
from cineapp.messages import tvshow_messages, movie_messages

profile_bp = Blueprint('profile',__name__,url_prefix='/my')

@profile_bp.route('/profile', methods=['GET', 'POST'])
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
                g.user.notifications["notif_show_add"] = form.notif_show_add.data
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
                                        return redirect(url_for('profile.edit_user_profile'))

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

@profile_bp.route('/password', methods=['GET', 'POST'])
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
