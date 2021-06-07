# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import absolute_import
from cineapp import app, db, lm
from flask import render_template, flash, redirect, url_for, g, request, session, jsonify
from flask_login import login_required
from cineapp.models import User, FavoriteShow
from datetime import datetime
from .emails import favorite_update_notification
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm.exc import FlushError

@app.route('/json/favshow/set/<int:show>/<int:user>', methods=['POST'])
@login_required
def set_favorite_show(show,user):

	# Fetch the star level
	star_type=request.form["star_type"]

	# Update the database with the new status for the show
	favorite_show = FavoriteShow.query.get((show,user))

	if favorite_show is None:
		favorite_show = FavoriteShow(show_id=show,user_id=user,added_when=datetime.now(),deleted_when=None, star_type=star_type)
	else:
		favorite_show.star_type = star_type 

	# Check if we own that favorite object
	if g.user.id != favorite_show.user_id:
		return jsonify({ "status": "danger", "message": u"%s" % g.messages["flash_favorite_add_denied"] })

	# Add the object into the database
	try:
		db.session.add(favorite_show)
		db.session.commit()

		# Try to send the email
		favorite_update_notification(favorite_show,"add")
		return jsonify({ "status": "success", "message": u"%s" % g.messages["flash_favorite_add"], "star_type" : favorite_show.star_type_obj.serialize() })
			
	except IntegrityError:
		db.session.rollback()
		app.logger.error("Erreur SQL sur l'ajout du favori")
		return jsonify({ "status": "danger", "message": u"%s" % g.messages["flash_favorite_already_exists"] })

	except Exception as e:
		db.session.rollback()
		print(e)
		app.logger.error("Erreur générale sur l'ajout du favori")
		return jsonify({ "status": "danger", "message": u"%s" % g.messages["flash_favorite_add_failed"] })

@app.route('/json/favshow/delete/<int:show>/<int:user>', methods=['GET'])
@login_required
def delete_favorite_show(show,user):

	# Update the database with the new status for the show
	favorite_show = FavoriteShow.query.get((show,user))

	# Check if we have something to delete before continue
	if favorite_show is None:
		return jsonify({ "status": "danger", "message": u"%s" % g.messages["flash_favorite_unknown"] })

	# Check if we own that favorite object
	if g.user.id != favorite_show.user_id:
		return jsonify({ "status": "danger", "message": u"%s" % g.messages["flash_favorite_delete_denied"] })

	# Add the object into the database
	try:
		db.session.delete(favorite_show)
		db.session.commit()

		# Try to send the email
		favorite_update_notification(favorite_show,"delete")
		return jsonify({ "status": "success", "message": u"%s" % g.messages["flash_favorite_delete"] })
			
	except IntegrityError:
		db.session.rollback()
		app.logger.error("Erreur SQL sur la suppression du favori")
		return jsonify({ "status": "danger", "message": u"%s" % g.messages["flash_favorite_unavailable"] })

	except Exception as e:
		db.session.rollback()
		print(e)
		app.logger.error("Erreur générale sur la suppression du favori")
		return jsonify({ "status": "danger", "message": u"%s" % g.messages["flash_favorite_delete_failed"] })
