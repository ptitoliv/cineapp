# -*- coding: utf-8 -*-

from __future__ import print_function
from cineapp import lm
from flask import Blueprint, render_template, flash, redirect, url_for, g, request, session, current_app as app
from flask_login import login_user, logout_user, current_user, login_required
from flask_socketio import SocketIO, emit
from cineapp.models import db, ChatMessage, User
from cineapp.emails import chat_message_notification
from cineapp.push import notification_send
from cineapp.auth import guest_control
from datetime import datetime, timedelta
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
import re
from multiprocessing import Process

chat_bp = Blueprint('chat', __name__)

def transmit_message(message,notify=False):
	""" This functions sends a message on the socket
	    formatting the message correctly
	"""
	# Fetch the user we have in session
	# Since we can't use g here
	logged_user = session.get("user", None)

	# Format the message adding the day if needed
	cur_date = datetime.now()
	if cur_date - message.posted_when < timedelta(days=1):
		message_date_formatted = "Aujourd'hui - " + message.posted_when.strftime("%H:%M")
	else:
		message_date_formatted = message.posted_when.strftime("%d/%m/%Y - %H:%M")

	# Notify users only if we have to
	if notify==True:

		# Send a notification to all users excluding the user who typed the message
		for cur_user in User.query.all():

			if cur_user.id != logged_user.id:

				# Serialize subscriptions before forking to avoid sharing
				# the MySQL connection with the child process
				serialized_subs = [sub.serialize() for sub in cur_user.subscriptions]

				if len(serialized_subs) > 0:
					# Let's handle the notifications in another dedicated process
					# in order to avoid blocking the chat
					p = Process(target=notification_send, args=(serialized_subs, url_for('chat.chat'),message.posted_by.nickname + ":  " + message.message))
					p.start()

		# Check if we have a user name into the message
		user_named = set(re.findall(r'@\w+',message.message))

		# We found potentials users => Let's try to check if they are real one
		for cur_user in user_named:
			try:
				# Check if we have a registered user with that nickname
				user=User.query.filter(User.nickname==cur_user[1:]).first()
				
				if user != None and user.id != logged_user.id:
					# We found a user, let's send him a notification who is not ourself
					chat_message_notification(message,user)
			except Exception as e:
				print(e)

	# Send the message
	emit('message', { 'user': message.posted_by.nickname, 'date': message_date_formatted, 'avatar': message.posted_by.avatar, 'msg' : message.message, 'color' : message.posted_by.theme_color }, broadcast=True)

@chat_bp.route('/chat')
@login_required
@guest_control
def chat():
    return render_template('chat.html')

def register_socketio_handlers(socketio):

	@socketio.on('connect', namespace='/chat_ws')
	@login_required
	def chat_connection():
		app.logger.info("Connection detected")

		user = session.get("user", None)

		# Let's send the last 100 Messages on the socketio
		chat_messages = ChatMessage.query.order_by(desc(ChatMessage.posted_when)).limit(100).all()

		# Display the message into the chat box from the first to the last
		# We browse the list in reverse mod for that
		for cur_message in reversed(chat_messages):
			transmit_message(cur_message)


	@socketio.on('chat_message', namespace='/chat_ws')
	@login_required
	def chat_message(message):

		app.logger.info("Message sent detected")

		# Send message only if it is different from null
		if message["data"] != '':
			user = session.get("user", None)

			# Let's store the message into the database
			chat_message = ChatMessage(message=message["data"], posted_when=datetime.now(), user_id=user.id)

			try:
				db.session.add(chat_message)
				db.session.commit()

			except IntegrityError:
				db.session.rollback()
				app.logger.error("Impossible d'enregistrer le message en base")
				return False

			# Transmit the message
			transmit_message(chat_message,notify=True)

		else:
			# Let's log a warning message
			app.logger.warning("An empty message as been sent")	
