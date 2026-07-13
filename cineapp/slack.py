from builtins import str
from builtins import object
from flask import request
from slack import WebClient
import json
import re
import html2text

class SlackChannel(object):

        """Class describing a slack channel on which one we can send some notifications """

        def __init__(self,slack_token,channel_name):

                self.channel_name = channel_name
                self.slack_token = None

                # This is here we are going to send the Slack notification
                self.slack_token = WebClient(slack_token)

        def send_message(self,message,attachment=None,blocks=None):

                """ Function that sends a message using SLACK API"""
                # Send the message
                try:
                    self.slack_token.chat_postMessage(
                      channel=self.channel_name,
                      text=message,
                      attachments=attachment,
                      blocks=blocks,
                      link_names=1,
                      unfurl_links=False
                    )

                except Exception as e:
                        raise SystemError("Slack API Error")

def html_to_slack_mrkdwn(html):

        """ Convert a CKEditor-authored (HTML) rating comment to Slack mrkdwn.

        The comment is stored as HTML (see utils.sanitize_comment). Posting it
        raw to Slack rendered the tags literally and broke the layout, so we run
        it through html2text, configured for Slack's mrkdwn dialect: *bold*,
        _italic_, • bullets, and no hard line-wrapping (a source of the
        misalignment). Plain-text (tag-less) legacy comments pass through
        unchanged. """

        h = html2text.HTML2Text()
        h.body_width = 0          # no hard-wrapping
        h.strong_mark = "*"       # Slack bold
        h.emphasis_mark = "_"     # Slack italic
        h.ul_item_mark = "•"
        h.ignore_links = True
        h.ignore_images = True
        text = h.handle(html or "")
        # html2text pads block boundaries with extra blank lines and marks hard
        # breaks with trailing spaces — normalise both so the quote reads clean.
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

def slack_mark_notification(mark,app,show_type):

        # Create a Slack object
        if ("SLACK_TOKEN" in app.config and app.config["SLACK_TOKEN"] != None) and app.config["SLACK_NOTIFICATION_ENABLE"] == True and app.config["SLACK_NOTIFICATION_CHANNEL"][show_type] != None:
                try:
                        slack_channel = SlackChannel(app.config["SLACK_TOKEN"],app.config["SLACK_NOTIFICATION_CHANNEL"][show_type])
                        app.logger.info("Notification sur SLACK pour la note de %s sur le show(%s) %s" % (mark.user.nickname,show_type,mark.show.name))

                        # Same rich Block Kit card for every show type (movie / tvshow / videogame):
                        # linked title + overview with the poster as a small thumbnail (section
                        # accessory), the note in a prominent header, then the comment. TMDB links used
                        # to unfurl natively but we now render the card ourselves everywhere for a
                        # consistent, reliable preview (Slack no longer renders legacy attachment thumbs).
                        # Next steps consits in building the local fields that will be used to create the Block

                        # Build the comment field (stored as HTML → Slack mrkdwn)
                        comment_text = html_to_slack_mrkdwn(mark.comment)

                        # Score without a trailing ".0" (15.0 → "15", 15.5 → "15.5").
                        mark_str = ("%g" % mark.mark) if mark.mark is not None else "?"

                        # Extract the year from the release date                        
                        if mark.show.release_date:
                                year = " (%d)" % mark.show.release_date.year
                        else:
                                year = ""
                                
                        # Truncate the overview field if it's too long
                        overview = (mark.show.overview or "").strip()
                        if len(overview) > 300:
                                overview = overview[:299].rsplit(" ", 1)[0] + "…"
                        title = mark.show.name + year

                        # Build the clickable link (Show Title + URL)
                        section_text = "*<%s|%s>*" % (mark.show.url, title)

                        # Append the overview to the section text
                        if overview:
                                section_text += "\n" + overview

                        # Append the mark to the section_text
                        section_text += "\n\n⭐ *Note de @%s:  %s/20*" % (mark.user.nickname,mark_str)

                        # Now let's build the Section block with the built section_text
                        section_block = { "type": "section", "text": { "type": "mrkdwn", "text": section_text } }

                        # If we have a poster, build the accessory section
                        if mark.show.poster_path:
                                poster_url = request.url_root.rstrip("/") + app.config["POSTERS_URL"] + mark.show.poster_path
                                section_block = dict(section_block, accessory={ "type": "image", "image_url": poster_url, "alt_text": title })
                                
                        # Blocks: the card, then the comment as its own full-width section
                        # (below the card, not squeezed beside the poster thumbnail).
                        blocks = [section_block]
                        if comment_text:
                                blocks.append({ "type": "section", "text": { "type": "mrkdwn", "text": "> " + comment_text.replace("\n", "\n> ") } })

                        # Send the message
                        slack_channel.send_message(message=title, blocks=blocks)
                        return 0

                except Exception as e:
                        app.logger.error("Impossible d'envoyer l'URL du film sur SLACK: %s",str(e))
                        return 1
        else:
                return -1
