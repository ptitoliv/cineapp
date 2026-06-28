from cineapp import lm
from flask_login import login_required
from flask import Blueprint, jsonify, session, g, url_for, request, current_app as app
from pywebpush import webpush, WebPushException
from cineapp.models import PushNotification
import json, traceback, datetime, time
from cineapp.auth import guest_control
from cineapp.models import db

push_bp = Blueprint('push', __name__)

@push_bp.route('/notifications/subscribe', methods=['POST'])
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

def notification_send(subscriptions,chat_url,chat_message):

    # This function runs in a forked child process (see chat.py). The DB pool is
    # inherited from the parent and must not be reused as-is: reset it once here
    # without closing the connections still in use by the parent (close=False).
    db.engine.dispose(close=False)

    for cur_subscription in subscriptions:
        try:
            expiration_date = int(time.mktime((datetime.datetime.now() + datetime.timedelta(hours=12)).timetuple()))
            webpush(cur_subscription,
            data=json.dumps({ "url":chat_url, "message_title": "Message depuis le chat", "message": chat_message }) ,
            vapid_private_key=app.config["NOTIF_PRIVATE_KEY_PATH"],
            vapid_claims={
            "sub": "mailto:cineapp@ptitoliv.net",
            "exp": expiration_date
            }
        )
        except WebPushException as ex:
            # If there is an error let's log it
            app.logger.error("Web push notification failed: %s", repr(ex))
            app.logger.error(traceback.format_exc())

            # 404/410 means the endpoint is gone; 403 means its VAPID
            # credentials no longer match ours (e.g. key rotation). In every
            # case the subscription can never be delivered again as-is, so
            # purge it: the browser re-subscribes with the current key on its
            # next visit.
            if ex.response is not None and ex.response.status_code in (403, 404, 410):
                try:
                    PushNotification.query.filter_by(endpoint_id=cur_subscription["endpoint"]).delete()
                    db.session.commit()
                    app.logger.info("Dead push subscription %s purged", cur_subscription["endpoint"])
                except Exception as e:
                    db.session.rollback()
                    app.logger.error("Unable to purge dead push subscription: %s", repr(e))
    
def notification_unsubscribe(sub):
    try:
        db.session.delete(sub)
        db.session.commit()
        app.logger.info('User subscription correctly delete from database')
        return True
    except Exception as e:
        app.logger.error('Unable to remove subscription user in database %s', repr(e))
        return False
