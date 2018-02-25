import os
import sys
from multiprocessing import Queue
from threading import Thread
import re
from slackclient import SlackClient
import analytics
from message import MessageManager
from enum import Enum
import logging

MOST_USED_REACTS = 'most_used_reacts'
MOST_REACTED_TO_MESSAGES = 'most_reacted_to_messages'
MOST_UNIQUE_REACTS_ON_POST = 'most_unique_reacts_on_post'
REACTS_TO_WORDS = 'reacts_to_words'
REACT_BUZZWORDS = 'react_buzzwords'

VALID_COMMANDS = [MOST_USED_REACTS, MOST_REACTED_TO_MESSAGES, MOST_UNIQUE_REACTS_ON_POST, REACTS_TO_WORDS, REACT_BUZZWORDS]

authed_teams = {}
class Bot(object):
	def __init__(self):
		super(Bot, self).__init__()
		self.name = "reactanalyticsbot"
		self.emoji = ":robot_face:"
		# When we instantiate a new bot object, we can access the app
		# credentials we set earlier in our local development environment.
		self.oauth = {"client_id": os.environ.get("CLIENT_ID"),
					  "client_secret": os.environ.get("CLIENT_SECRET"),
					  # Scopes provide and limit permissions to what our app
					  # can access. It's important to use the most restricted
					  # scope that your app will need.
					  "scope": "bot"}
		self.bot_access_token = os.environ.get('BOT_ACCESS_TOKEN')
		self.verification = os.environ.get("VERIFICATION_TOKEN")
		self.bot_client = SlackClient(self.bot_access_token)
		self.workspace_client = SlackClient(os.environ.get('ACCESS_TOKEN'))
		self.users = {} # user_id : {'user_name' : user_name, 'display_name' : display_name}
		self.channels = {} #channel_id : channel_name
		self.message_manager = MessageManager(self.load_message_history())
		self.event_queue = Queue()
		self.load_users()
		event_thread = Thread(target=self.event_handler_loop)
		event_thread.start()

	'''
	API INTERACTIONS
	'''
	def load_users(self):
		users_response = self.bot_client.api_call('users.list')
		if users_response['ok']:
			users = users_response['members']
			for user in users:
				user_id = user['id']
				user_name = user['name']
				user_info = {'user_name' : user_name}
				if 'display_name' in user['profile']:
					user_info['display_name'] = user['profile']['display_name']
				self.users[user_id] = user_info
		else:
			#raise Exception('Unable to load users: ' + )
			logging.getLogger(__name__).error(msg="Unable to load users: " + users_response['error'])

	def load_channels(self):
		list_response = self.workspace_client.api_call('channels.list')
		if not list_response['ok']:
			logging.getLogger(__name__).error(msg='Failed to get channel list: ' + list_response['error'])
			return
		for channel in list_response['channels']:
			self.channels[channel['id']] = channel['name']

	def load_message_history(self):
		if not self.channels:
			self.load_channels()
		messages = {}
		for channel in self.channels:
			messages[channel] = self.get_channel_message_history(channel)
		return messages

	def get_channel_message_history(self, channel_id):
		response = self.workspace_client.api_call('channels.history', channel=channel_id)
		if not response['ok']:
			logging.getLogger(__name__).error(msg='Failed to get channel history for ' + channel_id + ': ' + response['error'])
		else:
			return response['messages']

	# Given a channel ID checks if it's a direct message
	def is_dm_channel(self, channel_id):
		im_list_response = self.workspace_client.api_call('im.list')
		if im_list_response['ok']:
			im_channels = [im['id'] for im in im_list_response['ims']]
			return channel_id in im_channels
		else:
			return False

	def send_dm(self, user_id, message):
		new_dm = self.bot_client.api_call('im.open',
										  user=user_id)

		if not new_dm['ok']:
			return False

		channel_id = new_dm['channel']['id']
		post_msg = self.bot_client.api_call('chat.postMessage',
											channel=channel_id,
											username=self.name,
											text=message)
		return post_msg['ok']

	def auth(self, code):
		auth_response = self.bot_client.api_call('oauth.access',
												 client_id=self.oauth['client_id'],
												 client_secret=self.oauth['client_secret'],
												 code=code)
		if 'team_id' in auth_response:
			team_id = auth_response['team_id']
			authed_teams[team_id] = {'bot_token':
									auth_response['bot']['bot_access_token']}
		else:
			return False

		self.bot_client = SlackClient(authed_teams[team_id]['bot_token'])
		return True

	def auth_token(self, token):
		auth_response = self.bot_client.api_call('auth.test',
												 token=token)
		return auth_response['ok']

	'''
	EVENT HANDLERS
	'''

	def on_event(self, event_type, slack_event):
		self.event_queue.put(Event(event_type, slack_event))

	def handle_api_event(self, event):
		slack_event = event.event_info
		event_type = slack_event['event']['type']
		channel_id = slack_event['event']['item']['channel']

		if self.is_dm_channel(channel_id):
			return

		if event_type == 'reaction_added':
			return self.reaction_added(slack_event)
		elif event_type == 'reaction_removed':
			print('removed')
			return self.reaction_removed(slack_event)
		elif event_type == 'message':
			print('onMessage')
			return self.message_posted(slack_event)

	def reaction_added(self, slack_event):
		event = slack_event['event']
		react_name = event['reaction']
		user_id = event['user']
		channel_id = event['item']['channel']
		time_stamp = event['item']['ts']
		self.message_manager.add_react(channel_id, time_stamp, user_id, react_name)

	def reaction_removed(self, slack_event):
		event = slack_event['event']
		react_name = event['reaction']
		user_id = event['user']
		channel_id = event['item']['channel']
		time_stamp = event['item']['ts']
		self.message_manager.remove_react(channel_id, time_stamp, user_id, react_name)

	def message_posted(self, slack_event):
		event = slack_event['event']
		channel_id = event['channel']
		user_id = event['user']
		time_stamp = event['ts']
		text = event['text']
		self.message_manager.add_message(channel_id, time_stamp, user_id, text)

	def handle_slash_command(self, event):
		event = event.event_info
		token = event['token']

		if not self.auth_token(token):
			return

		text = event['text'].split(' ')
		user_id = event['user_id']
		command = text[0]
		args = ""
		#check if there are any args
		if len(text) > 1:
			args = ' '.join(text[1:])

		if command == MOST_USED_REACTS:
			response = self.most_used_reacts(args)
		elif command == MOST_REACTED_TO_MESSAGES:
			response = self.most_reacted_to_message(args)
		elif command == MOST_UNIQUE_REACTS_ON_POST:
			response = self.most_unique_reacts_on_post(args)
		elif command == REACTS_TO_WORDS:
			response = self.reacts_to_words(args)
		elif command == REACT_BUZZWORDS:
			response = self.react_buzzwords(args)

		self.send_dm(user_id, response)


	def most_reacted_to_message(self, text):
		re_object = re.search('(?<=\@)(.*?)(?=\|)', text)
		result_str = []
		if not re_object:
			result_str.append('Most reacted to posts\n')
			msgs = analytics.most_reacted_to_posts(self.message_manager)
		else:
			user_id = re_object.group(0)
			result_str.append('Most reacted to posts for ' + self.users[user_id] + '\n')
			msgs = analytics.most_reacted_to_posts(self.message_manager, re_object.group(0))

		for msg in msgs:
			result_str.append(str(self.message_manager.get_message_text(msg[0])) + ' : ' + str(msg[1]) + '\n')

		return ''.join(result_str)

	def most_used_reacts(self, text):
		user_id = re.search('(?<=\@)(.*?)(?=\|)', text)
		if not user_id:
			result = analytics.most_used_reacts(self.message_manager)
		else:
			result = analytics.favorite_reacts_of_user(self.message_manager, user_id.group(0))

		result_str = []
		for r in result:
			result_str.append(':')
			result_str.append(r[0])
			result_str.append(':')
			result_str.append(' : ' + str(r[1]) + '\n')
		return ''.join(result_str)

	def most_unique_reacts_on_post(self, text):
		channel_id = re.search('(?<=\#)(.*?)(?=\|)', text)
		result_str = []
		if not channel_id:
			result = analytics.most_unique_reacts_on_a_post(self.message_manager)
		else:
			result = analytics.most_unique_reacts_on_a_post(self.message_manager, channel_id.group(0))

		for r in result:
			result_str.append(self.message_manager.get_message_text(r[0]) + ' : ' + str(r[1]) + '\n')

		return ''.join(result_str)

	def reacts_to_words(self, text):
		return ' '.join(analytics.reacts_to_words(self.message_manager, self.users, self.channels))

	def react_buzzwords(self, text):

		reacts = re.findall('(?<=:)(.*?)(?=:)', text)
		reacts = [r for r in reacts if r.strip(' ')]
		print(reacts)
		result_str = []

		try:
			for r in reacts:
				result_str.append(r + ': ')
				react_buzzwords = [item[0] for item in analytics.react_buzzword(self.message_manager, r, self.users, self.channels)]

				if react_buzzwords:
					result_str.append(', '.join(react_buzzwords) + '\n')
				else:
					result_str.append('React not used\n')

		except:
			return 'something went wrong ' + str(sys.exc_info()[0])

		return ''.join(result_str)

	def event_handler_loop(self):
		while True:
			while not self.event_queue.empty():
				event = self.event_queue.get()
				if event.type == EventType.API_EVENT:
					self.handle_api_event(event)
				elif event.type == EventType.SLASH_COMMAND:
					self.handle_slash_command(event)



class Event(object):
	def __init__(self, event_type, event_info):
		self.type = event_type
		self.event_info = event_info

class EventType(Enum):
	SLASH_COMMAND = 0
	API_EVENT = 1
