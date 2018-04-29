from cineapp import app, db, lm
from flask.ext.login import login_required, request
from flask import jsonify, session, g, url_for
from pywebpush import webpush, WebPushException
from cineapp.models import PushNotification
import json, traceback, sys, datetime, time
from cineapp.auth import guest_control

@app.route('/notifications/subscribe', methods=['POST'])
@login_required
@guest_control
def notification_subscribe():

	app.logger.info('New user subscription !!')
	subscription = request.get_json()
	app.logger.info('User id: %s, Subscription data: %s' % (g.user.id,subscription))

	# Let's register the subscription message into the database
	push_notification = PushNotification(endpoint_id=subscription["endpoint"], public_key=subscription["keys"]["p256dh"], auth_token=subscription["keys"]["auth"], session_id=session.sid, user_id=g.user.id)

	# Store the subscription data into database
	try:
		db.session.add(push_notification)
		db.session.commit()
		app.logger.info('User subscription correctly stored into database')
	except Exception as e:
		app.logger.error('Unable to store subscription user in database %s', repr(e))
		return jsonify({ "status": "failure", "message": u"Unable to store subscription object into database" })
	
	return jsonify({ "status": "success", "message": u"Endpoint enregistray" })

def notification_send(text,active_subscriptions):

	for cur_active_sub in active_subscriptions:
		try:
		    expiration_date = time.mktime((datetime.datetime.now() + datetime.timedelta(hours=12)).timetuple())
		    webpush(cur_active_sub.serialize(),
			data=json.dumps({ "url":url_for('chat'), "message_title": "Message depuis le chat", "message": text }) ,
			vapid_private_key=app.config["NOTIF_PRIVATE_KEY_PATH"],
			vapid_claims={
			"sub": "mailto:ptitoliv@gmail.com",
			"exp": expiration_date
			}
    	)
		except WebPushException as ex:
		    # If there is an error let's remove the subscription
		    app.logger.error("Subscription for endpoint %s is incorrect ==> Delete it", cur_active_sub)
		    print traceback.print_exc(file=sys.stdout);

		    # Let's remove the notification
		    notification_unsubscribe(cur_active_sub)
			
		    print("I'm sorry, Dave, but I can't do that: {}", repr(ex))
                    print(ex.response.json())
	
def notification_unsubscribe(sub):
	try:
		db.session.delete(sub)
		db.session.commit()
		app.logger.info('User subscription correctly delete from database')
		return True
	except Exception as e:
		app.logger.error('Unable to remove subscription user in database %s', repr(e))
		return False
