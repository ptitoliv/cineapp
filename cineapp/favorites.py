# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import absolute_import
from cineapp import app, db, lm
from flask import render_template, flash, redirect, url_for, g, request, session, jsonify
from flask_login import login_required
from cineapp.models import User, FavoriteMovie
from datetime import datetime
from .emails import favorite_update_notification
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm.exc import FlushError

@app.route('/json/favmovie/set/<int:movie>/<int:user>', methods=['POST'])
@login_required
def set_favorite_movie(movie,user):

	# Fetch the star level
	star_type=request.form["star_type"]

	# Update the database with the new status for the movie
	favorite_movie = FavoriteMovie.query.get((movie,user))

	if favorite_movie is None:
		favorite_movie = FavoriteMovie(movie_id=movie,user_id=user,added_when=datetime.now(),deleted_when=None, star_type=star_type)
	else:
		favorite_movie.star_type = star_type 

	# Check if we own that favorite object
	if g.user.id != favorite_movie.user_id:
		return jsonify({ "status": "danger", "message": u"Vous n\'êtes pas autorisés à ajouter ce film en favori pour cet utilisateur" })

	# Add the object into the database
	try:
		db.session.add(favorite_movie)
		db.session.commit()

		# Try to send the email
		favorite_update_notification(favorite_movie,"add")
		return jsonify({ "status": "success", "message": u"Film défini en favori", "star_type" : favorite_movie.star_type_obj.serialize() })
			
	except IntegrityError:
		db.session.rollback()
		app.logger.error("Erreur SQL sur l'ajout du favori")
		return jsonify({ "status": "danger", "message": u"Film déja défini comme favori" })

	except Exception as e:
		db.session.rollback()
		print(e)
		app.logger.error("Erreur générale sur l'ajout du favori")
		return jsonify({ "status": "danger", "message": u"Impossible d'ajouter le film en favori" })

@app.route('/json/favmovie/delete/<int:movie>/<int:user>', methods=['GET'])
@login_required
def delete_favorite_movie(movie,user):

	# Update the database with the new status for the movie
	favorite_movie = FavoriteMovie.query.get((movie,user))

	# Check if we have something to delete before continue
	if favorite_movie is None:
		return jsonify({ "status": "danger", "message": u"Favori inexistant pour ce film pour cet utilisateur" })

	# Check if we own that favorite object
	if g.user.id != favorite_movie.user_id:
		return jsonify({ "status": "danger", "message": u"Vous n\'êtes pas autorisés à supprimer ce film en favori pour cet utilisateur" })

	# Add the object into the database
	try:
		db.session.delete(favorite_movie)
		db.session.commit()

		# Try to send the email
		favorite_update_notification(favorite_movie,"delete")

		return jsonify({ "status": "success", "message": u"Film supprimé des favoris" })
			
	except IntegrityError:
		db.session.rollback()
		app.logger.error("Erreur SQL sur la suppression du favori")
		return jsonify({ "status": "danger", "message": u"Le film n\'est pas enregistré comme un favori" })

	except Exception as e:
		db.session.rollback()
		print(e)
		app.logger.error("Erreur générale sur la suppression du favori")
		return jsonify({ "status": "danger", "message": u"Impossible de supprimer le film en favori" })
