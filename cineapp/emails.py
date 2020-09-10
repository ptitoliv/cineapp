# -*- coding: utf-8 -*-

from builtins import str
from flask import render_template,g
from flask_mail import Message
from cineapp import mail, db
from cineapp.models import User
from threading import Thread
from cineapp import app
import html2text, time, json

# Send mail into a dedicated thread in order to avoir the web app to wait
def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

# Wrapper function for sending mails using flask-mail plugin
def send_email(subject, sender, recipients, text_body):
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    thr = Thread(target=send_async_email, args=[app, msg])
    thr.start()

# Function which sends notifications to users when a movie is added
def add_movie_notification(movie):
	users = User.query.all()
	for cur_user in users:
		# Check if the cur_user is the logged user who added the movie
		# in order to change the mail text

		send_own_activity_mail=True

		if cur_user.id==g.user.id:
			you_user=True
		
			# Check if we must send an email for user own activity	
			if cur_user.notifications != None and cur_user.notifications["notif_own_activity"] == False:
				send_own_activity_mail=False
		else:
			you_user=False
	
		# Send the mail if we have too	
		if cur_user.notifications != None and cur_user.notifications["notif_movie_add"] == True and send_own_activity_mail==True:
			send_email('[Cineapp] - Ajout d\'un film' , app.config['MAIL_SENDER'],[ cur_user.email ] ,
			render_template('add_movie_notification.txt', dest_user=cur_user, add_user=g.user,movie=movie,you_user=you_user))

# Function which sends notifications to users when a movie is added
def mark_movie_notification(mark,notif_type):
	users = User.query.filter_by().all()

	# Convert the HTML content to text in order to have a nice display in the mail
	html_converter = html2text.HTML2Text()
	mark.comment=html_converter.handle(mark.comment).strip()

	for cur_user in users:
		# Check if the cur_user is the logged user who added the movie
		# in order to change the mail text

		send_own_activity_mail=True

		if cur_user.id==g.user.id:
			you_user=True

			# Check if we must send an email for user own activity	
			if cur_user.notifications != None and cur_user.notifications["notif_own_activity"] == False:
				send_own_activity_mail=False
		else:
			you_user=False

		# Send the mail if we have too	
		if cur_user.notifications != None and cur_user.notifications["notif_movie_add"] == True and send_own_activity_mail==True:
			try:
				if notif_type == "add":	
					send_email('[Cineapp] - Note d\'un film' , app.config['MAIL_SENDER'],[ cur_user.email ] ,
					render_template('mark_movie_notification.txt', dest_user=cur_user, add_user=g.user,mark=mark,you_user=you_user,notif_type=notif_type))
				elif notif_type == "update":
					send_email('[Cineapp] - Note mise à jour' , app.config['MAIL_SENDER'],[ cur_user.email ] ,
					render_template('mark_movie_notification.txt', dest_user=cur_user, add_user=g.user,mark=mark,you_user=you_user,notif_type=notif_type))
				elif notif_type == "homework":
					send_email('[Cineapp] - Devoir rempli' , app.config['MAIL_SENDER'],[ cur_user.email ] ,
					render_template('mark_movie_notification.txt', dest_user=cur_user, add_user=g.user,mark=mark,you_user=you_user,notif_type=notif_type))

				return 0
			except:
				app.logger.error("Impossible d'envoyer le mail: %s",str(e))
				return 1

	# Everything has been done correctly ==> return 0
	return 0

# Function which sends notification to user who received an homework
# For the homework, just send a mail to the user who has to handle the homework.
def add_homework_notification(mark):

	# Check if notifications are enabled for the destination user
	if mark.user.notifications != None and mark.user.notifications["notif_homework_add"] == True:
		try:
			send_email('[Cineapp] - Attribution d\'un devoir', app.config['MAIL_SENDER'],[ mark.user.email ],
			render_template('add_homework_notification.txt', dest_user=mark.user, homework_who=mark.homework_who_user, movie=mark.movie))
			return 0
		except:
			# We couldn't send the mail
			return 1
	else:
		# Display a message that the user don't want to be notified
		return 2

# Function which sends notification when an homework has been cancelled
# Send a notification to the user who cancelled the homework and another to
# the destination user the homework was for
def delete_homework_notification(mark):

	# Check if notifications are enabled for the user
	if mark.user.notifications != None and mark.user.notifications["notif_homework_add"] == True:
		try:
			send_email('[Cineapp] - Annulation d\'un devoir', app.config['MAIL_SENDER'],[ mark.user.email ],
			render_template('_homework_notification.txt', dest_user=mark.user, homework_who=mark.homework_who_user, movie=mark.movie))
			return 0
		except:
			# We couldn't send the mail
			return 1
	else:
		# Display a message that the user don't want to be notified
		return 2

# Function which sends notification to user when a movie has been updated into the database
def update_movie_notification(notif):
	users = User.query.filter_by().all()
	for cur_user in users:
		# Check if the cur_user is the logged user who added the movie
		# in order to change the mail text

		send_own_activity_mail=True

		if cur_user.id==g.user.id:
			you_user=True

			# Check if we must send an email for user own activity	
			if cur_user.notifications != None and cur_user.notifications["notif_own_activity"] == False:
				send_own_activity_mail=False
		else:
			you_user=False
	
		# Send the mail if we have too	
		if cur_user.notifications != None and cur_user.notifications["notif_movie_add"] == True and send_own_activity_mail==True:
			send_email('[Cineapp] - Modification d\'un film' , app.config['MAIL_SENDER'],[ cur_user.email ] ,
			render_template('update_movie_notification.txt', dest_user=cur_user, add_user=g.user,notif=notif,you_user=you_user))

# Function which sends notification to user when a comment has been posted on a mark
def mark_comment_notification(mark_comment,notif_type):
	users = User.query.filter_by().all()

	# Check if the comment is posted by a user on his own mark
	if mark_comment.user.id==mark_comment.mark.user.id:
		own_mark_user=True
	else:
		own_mark_user=False

	for cur_user in users:

		send_own_activity_mail=True

		# Check if the logged user posted the comment
		if cur_user.id==g.user.id:
			you_user=True

			# Check if we must send an email for user own activity	
			if cur_user.notifications != None and "notif_own_activity" in cur_user.notifications and cur_user.notifications["notif_own_activity"] == False:
				send_own_activity_mail=False
		else:
			you_user=False

		# Check if the comment refers to a mark for the logged user
		if cur_user.id==mark_comment.mark.user.id:
			you_dest_user=True
		else:
			you_dest_user=False

		# Send the mail if we have too	
		if cur_user.notifications != None and "notif_comment_add" in cur_user.notifications and cur_user.notifications["notif_comment_add"] == True and send_own_activity_mail==True:

			# Check the kind of mail we must send considering the notification type
			if notif_type == "add_mark_comment":
				mail_title = "Ajout d\'un commentaire"
				notif_template = "mark_comment_notification.txt"

			elif notif_type == "edit_mark_comment":

				mail_title = "Modification d\'un commentaire"
				notif_template = "mark_update_comment_notification.txt"

			elif notif_type == "delete_mark_comment":

				mail_title = "Suppression d\'un commentaire"
				notif_template = "mark_delete_comment_notification.txt"

			send_email('[Cineapp] - ' + mail_title , app.config['MAIL_SENDER'],[ cur_user.email ] ,
			render_template(notif_template, dest_user=cur_user, mark_comment=mark_comment, you_user=you_user,you_dest_user=you_dest_user,own_mark_user=own_mark_user))

# Function which sends notification to user when the favorite/star status has been updated for a movie
def favorite_update_notification(favorite_movie,notif_type):
	users = User.query.filter_by().all()

	for cur_user in users:

		send_own_activity_mail=True

		# Check if the logged user posted the comment
		if cur_user.id==g.user.id:
			you_user=True

			# Check if we must send an email for user own activity	
			if cur_user.notifications != None and "notif_own_activity" in cur_user.notifications and cur_user.notifications["notif_own_activity"] == False:
				send_own_activity_mail=False
		else:
			you_user=False

		# Send the mail if we have too	
		if cur_user.notifications != None and "notif_favorite_update" in cur_user.notifications and cur_user.notifications["notif_favorite_update"] == True and send_own_activity_mail==True:

			# Check the kind of mail we must send considering the notification type
			if notif_type == "add":
				mail_title = "Ajout d\'un film en favori"
				notif_template = "favorite_update_notification.txt"

			elif notif_type == "delete":
				mail_title = "Suppression d\'un film favori"
				notif_template = "favorite_update_notification.txt"

			send_email('[Cineapp] - ' + mail_title , app.config['MAIL_SENDER'],[ cur_user.email ] ,
			render_template(notif_template, dest_user=cur_user, favorite_movie=favorite_movie, you_user=you_user, notif_type=notif_type))

# Function that sends a notification when a user is named on the chat
def chat_message_notification(message,user):

	if user.notifications != None and "notif_chat_message" in user.notifications and user.notifications["notif_chat_message"] == True:

		app.logger.info("Sending mail for chat quote to %s "% user.email)
		send_email('[Cineapp] - Message depuis le chat' , app.config['MAIL_SENDER'],[ user.email ] ,
		render_template('chat_message_notification.txt', dest_user=user, message=message))
