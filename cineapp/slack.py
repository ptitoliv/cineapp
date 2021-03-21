from builtins import str
from builtins import object
from slack import WebClient
import json

class SlackChannel(object):

        """Class describing a slack channel on which one we can send some notifications """

        def __init__(self,slack_token,channel_name):

                self.channel_name = channel_name
                self.slack_token = None
                
                # This is here we are going to send the Slack notification
                self.slack_token = WebClient(slack_token)
                
        def send_message(self,message,attachment=None):

                """ Function that sends a message using SLACK API"""
                # Send the message
                response=self.slack_token.chat_postMessage(
                  channel=self.channel_name,
                  text=message,
                  attachments=attachment,
                  link_names=1,
                  unfurl_links=True
                )

                # Return the result
                if response["ok"] == False:
                        raise SystemError("Slack API Error : %s" % response["error"])

def slack_mark_notification(mark,app):

        # Create a Slack object
        if "SLACK_TOKEN" in app.config and app.config["SLACK_NOTIFICATION_CHANNEL"]:
                slack_channel = SlackChannel(app.config["SLACK_TOKEN"],app.config["SLACK_NOTIFICATION_CHANNEL"])
                app.logger.info("Notification sur SLACK pour la note de %s sur le film %s" % (mark.user.nickname,mark.movie.name))
                try:
                        attachment = json.dumps([
                            {
                                "text": mark.comment
                            }
                        ])

                        # We encode as str in order to avoid SLACK Api Parsing when unfurling the URL
                        slack_channel.send_message(message="<" + mark.movie.url + "?language=fr|" + mark.movie.name + ">") 
                        slack_channel.send_message(message="Note de @%s: *%s*" % (mark.user.nickname, str(mark.mark)) ,attachment=attachment)
                        return 0

                except Exception as e:
                        app.logger.error("Impossible d'envoyer l'URL du film sur SLACK: %s",str(e))
                        return 1
        else:
                return -1

