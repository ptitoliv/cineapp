# -*- coding: utf-8 -*-

from __future__ import print_function
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask
from flask_login import login_user, logout_user, current_user, login_required, LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask import Flask, session
from flask_session import Session
from flask_mail import Mail
from flask_babel import Babel
import logging, sys, os
from logging.handlers import RotatingFileHandler
from flask_socketio import SocketIO
from flask_migrate  import Migrate
from flask_msearch import Search

app = Flask(__name__)

# Create ProxyFix middleware in order to handle the HTTP headers sent by apache
# Used for correct url_for generation
app.wsgi_app = ProxyFix(app.wsgi_app)

# Global Variables
app.config['VERSION'] = "3.0.0"
app.config['GRAVATAR_URL'] = "https://www.gravatar.com/avatar/"
app.config['GRAPH_LIST'] = [
        { "graph_endpoint": "graphs.graph_by_mark", "graph_label": u"Répartition par note", "movie": True, "tvshow": True },
		{ "graph_endpoint": "graphs.graph_by_mark_percent", "graph_label": u"Répartition par note (en %)", "movie": True, "tvshow": True  },
		{ "graph_endpoint": "graphs.graph_by_mark_interval", "graph_label": u"Répartition par intervalle", "movie": True, "tvshow": True  },
		{ "graph_endpoint": "graphs.graph_by_type", "graph_label": u"Répartition par type", "movie": True, "tvshow": True  },
		{ "graph_endpoint": "graphs.graph_by_origin", "graph_label": u"Répartition par origine", "movie": True, "tvshow": True  },
		{ "graph_endpoint": "graphs.average_by_type", "graph_label": u"Moyenne par type", "movie": True, "tvshow": True  },
		{ "graph_endpoint": "graphs.average_by_origin", "graph_label": u"Moyenne par origine", "movie": True, "tvshow": True  },
		{ "graph_endpoint": "graphs.graph_by_year", "graph_label": u"Répartition par année", "movie": True, "tvshow": True  },
		{ "graph_endpoint": "graphs.graph_by_year_theater", "graph_label": u"Films vus au ciné", "movie": True, "tvshow": False  },
		{ "graph_endpoint": "graphs.average_by_year", "graph_label": u"Moyenne par année", "movie": True, "tvshow": True  }
	]

# Upload image control
app.config['ALLOWED_MIMETYPES'] = [ 'image/png', 'image/jpeg']
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

# Initialize path with default values if necessary
if 'AVATARS_URL' not in app.config:
	app.config['AVATARS_URL'] = "/static/avatars/"

if 'POSTERS_URL' not in app.config:
	app.config['POSTERS_URL'] = "/static/posters/"

# TMVDB parameters
app.config['TMVDB_BASE_URL'] = "https://themoviedb.org/"

# Configuration file reading
if os.environ.get('TEST') == "yes":
	app.config.from_pyfile('../configs/settings_test.cfg')
else:
	app.config.from_pyfile(os.path.join(app.root_path,'../configs/settings.cfg'))

# Intialize Slack configuration
if "SLACK_NOTIFICATION_ENABLE" in app.config:
    if app.config['SLACK_NOTIFICATION_ENABLE'] == True:
        
        # We want to use Slack notifications ==> Let's define channels
        app.config['SLACK_NOTIFICATION_CHANNEL']={}

        # For movies
        if "SLACK_NOTIFICATION_CHANNEL_MOVIES" in app.config and app.config['SLACK_NOTIFICATION_CHANNEL_MOVIES'] != None:
            app.config['SLACK_NOTIFICATION_CHANNEL']['movie']=app.config['SLACK_NOTIFICATION_CHANNEL_MOVIES']
        else:
            app.config['SLACK_NOTIFICATION_CHANNEL']['movie']=None

        # For tvshows
        if "SLACK_NOTIFICATION_CHANNEL_TVSHOWS" in app.config and app.config['SLACK_NOTIFICATION_CHANNEL_TVSHOWS'] != None:
            app.config['SLACK_NOTIFICATION_CHANNEL']['tvshow']=app.config['SLACK_NOTIFICATION_CHANNEL_TVSHOWS']
        else:
            app.config['SLACK_NOTIFICATION_CHANNEL']['tvshow']=None
else:
    print("SLACK_NOTIFICATION_ENABLE not defined in configuration file")
    sys.exit(2)

# Check if API_KEY is defined
for cur_item in [ "API_KEY", "SLACK_TOKEN" ]:
    if cur_item not in app.config:
            # Let's import it from environnment
            if os.environ.get(cur_item) != None:
                    app.config[cur_item] = os.environ.get(cur_item)

# Database Initialization
db = SQLAlchemy(app)
migrate = Migrate(app,db)

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

# FTS Engine
search=Search()
search.init_app(app)

##################
# Logging system #
##################

# Create the log directory if it doesn't exists
try:
	if not os.path.isdir(app.config['LOGDIR']):
		os.makedirs(app.config['LOGDIR'],0o755)
except:
	print("Unable to create " + app.config['LOGDIR'])
	sys.exit(2)

# Create the avatar directory if it doesn't exists
try:
	if not os.path.isdir(app.config['AVATARS_FOLDER']):
		os.makedirs(app.config['AVATARS_FOLDER'],0o755)
except:
	print("Unable to create " + app.config['AVATARS_FOLDER'])
	sys.exit(2)

# Open a file rotated every 100MB
file_handler = RotatingFileHandler(os.path.join(app.config['LOGDIR'],'cineapp.log'), 'a', 100 * 1024 * 1024, 10)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
app.logger.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.info('Cineapp startup')

# Blueprint Registration
from cineapp.shows import show_bp
from cineapp.homeworks import homework_bp
from cineapp.profile import profile_bp
from cineapp.graphs import graph_bp
app.register_blueprint(show_bp)
app.register_blueprint(homework_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(graph_bp)

from cineapp import views, models, jinja_filters, chat, comments, favorites, jinja_testers
