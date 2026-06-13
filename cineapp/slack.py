from builtins import str
from builtins import object
from flask import request
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
                try:
                    response=self.slack_token.chat_postMessage(
                      channel=self.channel_name,
                      text=message,
                      attachments=attachment,
                      link_names=1,
                      unfurl_links=True
                    )

                except Exception as e:
                        raise SystemError("Slack API Error")

def slack_mark_notification(mark,app,show_type):

        # Create a Slack object
        if ("SLACK_TOKEN" in app.config and app.config["SLACK_TOKEN"] != None) and app.config["SLACK_NOTIFICATION_ENABLE"] == True and app.config["SLACK_NOTIFICATION_CHANNEL"][show_type] != None:
                try:
                        slack_channel = SlackChannel(app.config["SLACK_TOKEN"],app.config["SLACK_NOTIFICATION_CHANNEL"][show_type])
                        app.logger.info("Notification sur SLACK pour la note de %s sur le show(%s) %s" % (mark.user.nickname,show_type,mark.show.name))
                        attachment = json.dumps([
                            {
                                "text": mark.comment
                            }
                        ])

                        if show_type == "videogame":
                                # IGDB links never unfurl (igdb.com returns 403 to bots), so we build
                                # the preview card ourselves, TMDB-style, with the poster served from
                                # /static/posters as the thumbnail (reachable on prod, not on a local dev box)
                                if mark.show.release_date:
                                        year = " (%d)" % mark.show.release_date.year 
                                else:
                                        year = ""
                                
                                # Truncate the overview field if it's too long
                                overview = (mark.show.overview or "").strip()
                                if len(overview) > 300:
                                        overview = overview[:299].rsplit(" ", 1)[0] + "…"
                               
                                # Let's generate the Slack card
                                card = {
                                    "author_name": "IGDB",
                                    "title": mark.show.name + year,
                                    "title_link": mark.show.url + "?language=fr",
                                    "fallback": mark.show.name + year,
                                    "text": overview
                                }

                                # Add the poster link if there is one
                                if mark.show.poster_path:
                                        card["thumb_url"] = request.url_root.rstrip("/") + app.config["POSTERS_URL"] + mark.show.poster_path
                                slack_channel.send_message(message="", attachment=json.dumps([card]))
                        else:
                                # We encode as str in order to avoid SLACK Api Parsing when unfurling the URL
                                slack_channel.send_message(message="<" + mark.show.url + "?language=fr|" + mark.show.name + ">")
                        slack_channel.send_message(message="Note de @%s: *%s*" % (mark.user.nickname, str(mark.mark)) ,attachment=attachment)
                        return 0

                except Exception as e:
                        app.logger.error("Impossible d'envoyer l'URL du film sur SLACK: %s",str(e))
                        return 1
        else:
                return -1
