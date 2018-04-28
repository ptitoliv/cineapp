from slackclient import SlackClient
import json

class SlackChannel:

	"""Class describing a slack channel on which one we can send some notifications """

	def __init__(self,slack_token,channel_name):

                self.channel_id = None
                self.channel_name = None
		self.slack_token = None
		
                # This is here we are going to send the Slack notification
                self.slack_token = SlackClient(slack_token)
                
                # Let's try to find a match with the channel name
                response=self.slack_token.api_call("channels.list")
		
		if response["ok"] == True:
			for cur_channel in response["channels"]:
				if cur_channel["name"] == channel_name:
					self.channel_id = cur_channel["name"]
					self.channel_name = cur_channel["id"]
					break;
                
			# If there is no matching with the channels list, let's try with the private groups
			if self.channel_id == None:
				response=self.slack_token.api_call("groups.list")
				for cur_channel in response["groups"]:
					if cur_channel["name"] == channel_name:
						self.channel_id = cur_channel["name"]
						self.channel_name = cur_channel["id"]
						break;


	def send_message(self,message,attachment=None):

		""" Function that sends a message using SLACK API"""
		# Send the message
		response=self.slack_token.api_call(
		  "chat.postMessage",
		  channel=self.channel_id,
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
	if app.config.has_key("SLACK_TOKEN") and app.config["SLACK_NOTIFICATION_CHANNEL"]:
		slack_channel = SlackChannel(app.config["SLACK_TOKEN"],app.config["SLACK_NOTIFICATION_CHANNEL"])
		app.logger.info("Notification sur SLACK pour la note de %s sur le film %s" % (mark.user.nickname,mark.movie.name))
		try:
			attachment = json.dumps([
			    {
				"text": mark.comment
			    }
			])

			# We encode as str in order to avoid SLACK Api Parsing when ufurling the URL
			slack_channel.send_message(message="<" + mark.movie.url.encode("utf-8") + "?language=fr|" + mark.movie.name.encode("utf-8") + ">")
			slack_channel.send_message(message="Note de @%s: *%s*" % (mark.user.nickname, str(mark.mark)) ,attachment=attachment)
			return 0

		except Exception as e:
			app.logger.error("Impossible d'envoyer l'URL du film sur SLACK: %s",str(e))
			return 1
	else:
		return -1

