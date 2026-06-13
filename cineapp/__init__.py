# -*- coding: utf-8 -*-

from __future__ import print_function
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask
from flask_login import login_user, logout_user, current_user, login_required, LoginManager
from flask import Flask, session, g
from flask_session import Session
from flask_babel import Babel
import logging, sys, os, locale
from logging.handlers import RotatingFileHandler
from flask_socketio import SocketIO
from flask_migrate  import Migrate
from datetime import datetime
from cineapp.messages import tvshow_messages, movie_messages, videogame_messages
from cineapp.forms import SearchShowForm
from cineapp.models import Movie, TVShow, VideoGame
from cineapp.jinja_filters import date_format, minutes_to_human_duration
from cineapp.jinja_testers import is_movie, is_tvshow, is_videogame
from past.builtins import basestring

lm = LoginManager()
sess = Session()
babel = Babel()
socketio=SocketIO()

def create_app(config_path=None):

    # Leg's create the application
    app = Flask(__name__)

    # Register Jinja filters
    app.jinja_env.filters['minutes_to_human_duration'] = minutes_to_human_duration
    app.jinja_env.filters['date_format'] = date_format

    # Register Jinja testers
    app.jinja_env.tests['movie'] = is_movie
    app.jinja_env.tests['tvshow'] = is_tvshow
    app.jinja_env.tests['videogame'] = is_videogame


    @app.context_processor
    def inject_search_form():
    
        # Make the search form available in all templates (Including base.html)
        search_form = SearchShowForm()
        return dict(search_form=search_form)
    
    @app.before_request
    def before_request():
    
            # Store the current authenticated user into a global object
            # current_user set by flask
            # g set by flask
            g.user = current_user
    
            # Make the graph list available in the whole app
            g.graph_list = app.config['GRAPH_LIST']
    
            # Return the current date
            g.cur_date = datetime.now()
    
            # Define the mode (Movie or TVShow)
            g.app_mode = "tv"
            g.tvmdb_api_mode = "tv"
    
            # Set mode to movie by default
            if session.get('show_type') == None:
                app.logger.info("Le type de show n'est pas défini dans la session. Configuration à movie par défaut")
                session["show_type"] = "movie"
           
            # Configure g with the value stored in the session
            # TIP: g is only set for the current request and not globally to the session
            # For that: there is ... session
            g.show_type=session["show_type"]
    
            if g.show_type == "movie":
                g.messages=movie_messages
            elif g.show_type == "tvshow":
                g.messages=tvshow_messages
            elif g.show_type == "videogame":
                g.messages=videogame_messages

    # Create ProxyFix middleware in order to handle the HTTP headers sent by apache
    # Used for correct url_for generation
    app.wsgi_app = ProxyFix(app.wsgi_app)
    
    # Global Variables
    app.config['VERSION'] = "3.0.0"
    app.config['GRAVATAR_URL'] = "https://www.gravatar.com/avatar/"
    app.config['GRAPH_LIST'] = [
            { "graph_endpoint": "graphs.graph_by_mark", "graph_label": u"Répartition par note", "movie": True, "tvshow": True, "videogame": True },
            { "graph_endpoint": "graphs.graph_by_mark_percent", "graph_label": u"Répartition par note (en %)", "movie": True, "tvshow": True, "videogame": True  },
            { "graph_endpoint": "graphs.graph_by_mark_interval", "graph_label": u"Répartition par intervalle", "movie": True, "tvshow": True, "videogame": True  },
            { "graph_endpoint": "graphs.graph_by_type", "graph_label": u"Répartition par type", "movie": True, "tvshow": True, "videogame": True  },
            { "graph_endpoint": "graphs.graph_by_origin", "graph_label": u"Répartition par origine", "movie": True, "tvshow": True, "videogame": True  },
            { "graph_endpoint": "graphs.average_by_type", "graph_label": u"Moyenne par type", "movie": True, "tvshow": True, "videogame": True  },
            { "graph_endpoint": "graphs.average_by_origin", "graph_label": u"Moyenne par origine", "movie": True, "tvshow": True, "videogame": True  },
            { "graph_endpoint": "graphs.graph_by_year", "graph_label": u"Répartition par année", "movie": True, "tvshow": True, "videogame": True  },
            { "graph_endpoint": "graphs.graph_by_year_theater", "graph_label": u"Films vus au ciné", "movie": True, "tvshow": False, "videogame": False  },
            { "graph_endpoint": "graphs.average_by_year", "graph_label": u"Moyenne par année", "movie": True, "tvshow": True, "videogame": True  }
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

    # Import data from the configuration file
    if config_path != None and os.path.isfile(os.path.join(os.getcwd(),config_path)):
        if os.path.isabs(config_path):
            app.config.from_pyfile(config_path)
        else:
            app.config.from_pyfile(os.path.join(os.getcwd(),config_path))
    else:
        raise RuntimeError("Pas de fichier de configuration disponible à cet emplacement")
    
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

            # For videogames
            if "SLACK_NOTIFICATION_CHANNEL_VIDEOGAMES" in app.config and app.config['SLACK_NOTIFICATION_CHANNEL_VIDEOGAMES'] != None:
                app.config['SLACK_NOTIFICATION_CHANNEL']['videogame']=app.config['SLACK_NOTIFICATION_CHANNEL_VIDEOGAMES']
            else:
                app.config['SLACK_NOTIFICATION_CHANNEL']['videogame']=None
    else:
        raise RuntimeError ("SLACK_NOTIFICATION_ENABLE not defined in configuration file")
    
    # Check if API_KEY is defined
    for cur_item in [ "API_KEY", "SLACK_TOKEN", "DEEPL_API_KEY", "IGDB_CLIENT_ID", "IGDB_CLIENT_SECRET"  ]:
        if cur_item not in app.config:
                # Let's import it from environnment
                if os.environ.get(cur_item) != None:
                        app.config[cur_item] = os.environ.get(cur_item)
    
    # Database Initialization
    from cineapp.models import db
    db.init_app(app)
    migrate = Migrate(app,db)
    
    # Login manager init
    lm.init_app(app)
    lm.login_view = 'main.login'
    
    # Session Manager Init
    sess.init_app(app)
    
    # Mail engine init
    from cineapp.emails import mail
    mail.init_app(app)
    
    # Translation engine init
    babel.init_app(app)
    
    # SocketIO subsystem (For Chat feature)
    socketio.init_app(app)
    from cineapp.chat import register_socketio_handlers
    register_socketio_handlers(socketio)
       
    # Create missing directories if they don't exist
    for cur_dir in [ app.config['LOGDIR'], app.config['AVATARS_FOLDER'], app.config['POSTERS_PATH'] ]:
        try:
            if not os.path.isdir(cur_dir):
                os.makedirs(cur_dir,0o755)
        except:
            raise OSError("Impossible de créer " + cur_dir)
          
    ##################
    # Logging system #
    ##################
    
    # Open a file rotated every 100MB
    file_handler = RotatingFileHandler(os.path.join(app.config['LOGDIR'],'cineapp.log'), 'a', 100 * 1024 * 1024, 10)
    file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.info('Cineapp startup')

    # Set the process locale up front so strftime (the date_format filter) renders
    # French month/day names everywhere, instead of only after the dashboard sets
    # it. We only touch LC_TIME (dates) and fall back gracefully if the locale isn't
    # generated on the host.
    app_locale = app.config.get('LOCALE', 'fr_FR.UTF-8')
    try:
        locale.setlocale(locale.LC_TIME, app_locale)
    except locale.Error:
        app.logger.warning("Locale '%s' indisponible sur le système, dates non localisées", app_locale)

    # Blueprint Registration
    from .shows import show_bp
    from .homeworks import homework_bp
    from .profile import profile_bp
    from .graphs import graph_bp
    from .views import view_bp
    from .chat import chat_bp
    from .comments import comments_bp
    from .favorites import favorites_bp
    from .push import push_bp
    app.register_blueprint(view_bp)
    app.register_blueprint(show_bp)
    app.register_blueprint(homework_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(graph_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(comments_bp)
    app.register_blueprint(favorites_bp)
    app.register_blueprint(push_bp)
    
    from cineapp import views, models, jinja_filters, chat, comments, favorites, jinja_testers

    return app
