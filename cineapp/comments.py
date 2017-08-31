# -*- coding: utf-8 -*-

from cineapp import app, db, lm
from flask import render_template, flash, redirect, url_for, g, request, session, jsonify
from flask.ext.login import login_required
from cineapp.models import User, MarkComment
from datetime import datetime
from emails import mark_comment_notification
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm.exc import FlushError

@app.route('/json/add_mark_comment', methods=['POST'])
@login_required
def add_mark_comment():

	# Fetch the important informations we need to fill the chat message object
	comment = request.form["comment"]
	dest_user = request.form["dest_user"]
	movie_id = request.form["movie_id"]

	# Create the chat_message object
	mark_comment=MarkComment()
	mark_comment.user_id = g.user.id
	mark_comment.mark_user_id = dest_user
	mark_comment.mark_movie_id = movie_id
	mark_comment.posted_when = datetime.now()
	mark_comment.message = comment

	# Let's check if the message is empty or not
	# If the message is empty don't add it and return an error status
	if not comment:
		return jsonify( { "error":"Vous ne pouvez pas insérer un commentaire vide", "mark_comment": mark_comment.serialize() } )

	# Add the object into the database
	try:
		db.session.add(mark_comment)
		db.session.commit()
			
		# TODO : DO BETEER REALLY !!!!
		mark_comment.posted_when = mark_comment.posted_when.strftime('%d/%m/%Y - %H:%M:%S')

	except IntegrityError:
		db.session.rollback()

	# Try to send the email
	mark_comment_notification(mark_comment,"add_mark_comment")

	# Build the dict we're going to send to the frontend
	data_dict = { "user": g.user.serialize(), "mark_comment": mark_comment.serialize(), "mark_comment_number": MarkComment.query.filter(MarkComment.mark_user_id==dest_user,MarkComment.mark_movie_id==movie_id,MarkComment.deleted_when==None).count()}

	# Let's send the JSON Response to the frontend
	return jsonify(data_dict)

@app.route('/json/delete_mark_comment', methods=['POST'], endpoint="delete_mark_comment")
@app.route('/json/edit_mark_comment', methods=['POST'], endpoint="edit_mark_comment")
@login_required
def update_mark_comment():

	# Check if the comment exists
	comment_id = request.form["comment_id"]
	mark_comment = MarkComment.query.filter(MarkComment.markcomment_id==comment_id,MarkComment.deleted_when==None).first()

	if mark_comment is not None:

		# Update the comment only if the logged user is the owner
		if mark_comment.user_id != g.user.id:
			return jsonify( { "error":u"Vous ne pouvez supprimer que vos propres commentaires", "markcomment_id": comment_id } )

		# Let's check if we must do an edition or a deletion
		if request.endpoint == "delete_mark_comment":

			# Let's mark the comment as deleted
			mark_comment.message = u"Ce commentaire a été supprimé"
			mark_comment.deleted_when = datetime.now()

			# TODO : DO BETEER REALLY !!!!
			mark_comment.deleted_when = mark_comment.deleted_when.strftime('%Y-%m-%d %H:%M:%S')

		elif request.endpoint == "edit_mark_comment":

			# We are in edition mode => Update the comment text
			mark_comment.old_message = mark_comment.message
			mark_comment.message = request.form["comment_text"]

		# Update the comment
		try:
			db.session.add(mark_comment)
			db.session.commit()
			app.logger.info(u"Le commentaire %s a été supprimé" % (mark_comment.markcomment_id))
				
			# Try to send the email
			mark_comment_notification(mark_comment,request.endpoint)

		except IntegrityError:
			db.session.rollback()

	else:
		return jsonify( { "error":u"Commentaire inexistant ou déjà supprimé", "markcomment_id": comment_id } )

	# Let's send the MarkComment as a JSON object to the frontend
	return jsonify( { "operation": request.endpoint , "mark_comment": mark_comment.serialize(), "mark_comment_number": MarkComment.query.filter(MarkComment.mark_user_id==mark_comment.mark_user_id,MarkComment.mark_movie_id==mark_comment.mark_movie_id,MarkComment.deleted_when==None).count() })
