# -*- coding: utf-8 -*-

from werkzeug.contrib.fixers import ProxyFix
from flask import Flask
from flask.ext.login import login_user, logout_user, current_user, login_required, LoginManager
from flask.ext.sqlalchemy import SQLAlchemy
from flask import Flask, session
from flask.ext.session import Session
from flask.ext.mail import Mail
from flask.ext.babel import Babel
import logging, sys, os
from logging.handlers import RotatingFileHandler
from flask_socketio import SocketIO

app = Flask(__name__)

# Create ProxyFix middleware in order to handle the HTTP headers sent by apache
# Used for correct url_for generation
app.wsgi_app = ProxyFix(app.wsgi_app)

# Global Variables
app.config['VERSION'] = "2.1.2"
app.config['GRAVATAR_URL'] = "https://www.gravatar.com/avatar/"
app.config['GRAPH_LIST'] = [
		{ "graph_endpoint": "graph_by_mark", "graph_label": u"Répartition par note" },
		{ "graph_endpoint": "graph_by_mark_percent", "graph_label": u"Répartition par note (en %)" },
		{ "graph_endpoint": "graph_by_mark_interval", "graph_label": u"Répartition par intervalle" },
		{ "graph_endpoint": "graph_by_type", "graph_label": u"Répartition par type" },
		{ "graph_endpoint": "graph_by_origin", "graph_label": u"Répartition par origine" },
		{ "graph_endpoint": "average_by_type", "graph_label": u"Moyenne par type" },
		{ "graph_endpoint": "average_by_origin", "graph_label": u"Moyenne par origine" },
		{ "graph_endpoint": "graph_by_year", "graph_label": u"Répartition par année" },
		{ "graph_endpoint": "graph_by_year_theater", "graph_label": u"Films vus au ciné" },
		{ "graph_endpoint": "average_by_year", "graph_label": u"Moyenne par année" }
	]

# Upload image control
app.config['ALLOWED_MIMETYPES'] = [ 'image/png', 'image/jpeg']
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

# Initialize path with default values if necessary
if not app.config.has_key('AVATARS_URL'):
	app.config['AVATARS_URL'] = "/static/avatars/"

if not app.config.has_key('POSTERS_URL'):
	app.config['POSTERS_URL'] = "/static/posters/"

# TMVDB parameters
app.config['TMVDB_BASE_URL'] = "https://themoviedb.org/movie"

# Configuration file reading
if os.environ.get('TEST') == "yes":
	app.config.from_pyfile('../configs/settings_test.cfg')
else:
	app.config.from_pyfile(os.path.join(app.root_path,'../configs/settings.cfg'))

# Check if API_KEY is defined
if not app.config.has_key('API_KEY'):
	# Let's import it from environnment
	if os.environ.get('API_KEY') != None:
		app.config['API_KEY'] = os.environ.get('API_KEY')
	else:
		sys.exit(1)

# Database Initialization
db = SQLAlchemy(app)

# Login manager init
lm = LoginManager()
lm.init_app(app)
lm.login_view = 'login'

# Session Manager Init
sess = Session()
sess.init_app(app)

# Mail engine init
mail = Mail(app)

# Translation engine init
babel = Babel(app)

# SocketIO subsystem (For Chat feature)
socketio=SocketIO()
socketio.init_app(app)

##################
# Logging system #
##################

# Create the log directory if it doesn't exists
try:
	if not os.path.isdir(app.config['LOGDIR']):
		os.makedirs(app.config['LOGDIR'],0o755)
except:
	print "Unable to create " + app.config['LOGDIR']
	sys.exit(2)

# Create the avatar directory if it doesn't exists
try:
	if not os.path.isdir(app.config['AVATARS_FOLDER']):
		os.makedirs(app.config['AVATARS_FOLDER'],0o755)
except:
	print "Unable to create " + app.config['AVATARS_FOLDER']
	sys.exit(2)

# Open a file rotated every 100MB
file_handler = RotatingFileHandler(os.path.join(app.config['LOGDIR'],'cineapp.log'), 'a', 100 * 1024 * 1024, 10)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
app.logger.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.info('Cineapp startup')

from cineapp import views, models, jinja_filters, chat, comments, favorites
