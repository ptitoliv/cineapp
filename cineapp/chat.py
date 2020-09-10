# -*- coding: utf-8 -*-

from __future__ import print_function
from cineapp import app, lm, socketio, db
from flask import render_template, flash, redirect, url_for, g, request, session
from flask_login import login_user, logout_user, current_user, login_required
from flask_socketio import SocketIO, emit
from cineapp.models import ChatMessage, User
from cineapp.emails import chat_message_notification
from cineapp.push import notification_send
from cineapp.auth import guest_control
from datetime import datetime, timedelta
from sqlalchemy import desc
import re
from multiprocessing import Process

def transmit_message(message,notify=False):
	""" This functions sends a message on the socket
	    formatting the message correctly
	"""
	# Fetch the user we have in session
	# Since we can't use g here
	logged_user = session.get("user", None)

	# Check if a user is registered in the session
	if logged_user is None or not isinstance(logged_user, User):
		app.logger.error("Incorrect user object into the session")
		return False

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

				# Let's handle the notifications in another dedicated process
				# in order to avoid blocking the chat
				p = Process(target=notification_send, args=(message.posted_by.nickname + ":  " + message.message, cur_user.subscriptions))
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
	emit('message', { 'user': message.posted_by.nickname, 'date': message_date_formatted, 'avatar': message.posted_by.avatar, 'msg' : message.message }, broadcast=True)

@app.route('/chat')
@login_required
@guest_control
def chat():
    return render_template('chat.html')

@socketio.on('connect', namespace='/chat_ws')
@login_required
def chat_connection():
	app.logger.info("Connection detected")

	user = session.get("user", None)

	# Check if a user is registered in the session
	if user is None or not isinstance(user, User):
		app.logger.error("Incorrect user object into the session")
		return False

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

		# Check if a user is registered in the session
		if user is None or not isinstance(user, User):
			app.logger.error("Incorrect user object into the session")
			return False

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
