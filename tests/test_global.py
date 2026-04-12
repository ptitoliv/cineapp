# -*- coding: utf-8 -*-

from future import standard_library
standard_library.install_aliases()
import os, sys, json, requests, urllib.error
from urllib.request import urlopen
from cineapp import create_app, minutes_to_human_duration, date_format, socketio, slack
from cineapp.models import db, User, Type, Origin, Mark, Movie, TVShow, VideoGame, FavoriteShow, MarkComment, PushNotification, ChatMessage
from cineapp.emails import mail
from cineapp.jinja_testers import is_movie, is_tvshow, is_videogame
from cineapp.push import notification_send
from pywebpush import WebPushException
from datetime import datetime
from bcrypt import hashpw, gensalt
import unittest
from unittest.mock import patch
import tempfile
import shutil
import io
from bs4 import BeautifulSoup
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import FlushError
from flask_migrate import upgrade
from flask import url_for
from sqlalchemy import text

class FlaskrTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        # Create the appliction considering the factory pattern
        if os.getenv("CI") == "True":
            cls.app = create_app('tests/ressources/settings_tests_ci.cfg')
        else:
            cls.app = create_app('configs/settings_tests_local.cfg')

        # Init with default connection string
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.app.config['TESTING'] = True
        cls.app.config['MAIL_SUPPRESS_SEND'] = True
        cls.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        cls.client = cls.app.test_client()

        with cls.app.app_context():
            db.drop_all()
        
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.app.config['TESTING'] = True

        # Delete the directories if they exisits
        if os.path.isdir(os.path.join(cls.app.config['POSTERS_PATH'])):
                shutil.rmtree(cls.app.config['POSTERS_PATH'])
        
        if os.path.isdir(os.path.join(cls.app.config['AVATARS_FOLDER'])):
                shutil.rmtree(cls.app.config['AVATARS_FOLDER'])
        
        # Create directories
        os.makedirs(cls.app.config['POSTERS_PATH'])
        os.makedirs(cls.app.config['AVATARS_FOLDER'])

        # Create the database
        with cls.app.app_context():
            upgrade()
        
        # Create the default user for tests
        hashed_password=hashpw("toto1234".encode('utf-8'),gensalt())
        u = User()
        u.nickname="ptitoliv"
        u.password=hashed_password
        u.email="ptitoliv@ptitoliv.net"
        u.notifications={
            "notif_own_activity" : True,
            "notif_show_add" : True,
            "notif_mark_add": True,
            "notif_homework_add": True,
            "notif_comment_add": True,
            "notif_favorite_update": True,
            "notif_chat_message": True,
            "notif_slack": True
            }
        
        with cls.app.app_context():
            db.session.add(u)
            db.session.commit()

    @classmethod
    def tearDownClass(cls):

        # Remove directories
        shutil.rmtree(cls.app.config['POSTERS_PATH'])
        shutil.rmtree(cls.app.config['AVATARS_FOLDER'])
        
        with cls.app.app_context():
            db.session.commit()
            db.session.execute(text("DROP TABLE alembic_version"))
            db.drop_all()

    def test_00_utils_functions(self):

        """
            Unit test for utils functions
        """

        # Test minutes duration to human readable format conversion
        assert None == minutes_to_human_duration("NaN")
        assert "3h 0min" == minutes_to_human_duration(180)

        # Test date_format function
        assert "14/07/2023" == date_format("2023-07-14","%d/%m/%Y")
        assert None == date_format("NaN","%d/%m/%Y")

        # Test functions guessing object type
        new_movie = Movie()
        new_tvshow = TVShow()
        new_videogame = VideoGame()
        assert is_movie(new_movie) == True
        assert is_movie(new_tvshow) == False
        assert is_tvshow(new_tvshow) == True
        assert is_tvshow(new_movie) == False
        assert is_movie(None) == False
        assert is_tvshow(None) == False
        assert is_videogame(new_videogame) == True
        assert is_videogame(new_movie) == False
        assert is_videogame(None) == False

        # Model dunder / property coverage
        u = User()
        u.nickname = "repr_user"
        assert u.is_anonymous == False
        assert "repr_user" in repr(u)
        new_movie.name = "repr_show"
        assert "repr_show" in repr(new_movie)

    def test_01_populateUsers(self):
        with self.app.app_context():
            hashed_password=hashpw("toto1234".encode('utf-8'),gensalt())
            u = User()
            u.nickname="foo"
            u.password=hashed_password
            u.email="foo@bar.net"
            u.notifications={
                "notif_own_activity" : True,
                "notif_show_add" : True,
                "notif_mark_add": True,
                "notif_homework_add": True,
                "notif_comment_add": True,
                "notif_favorite_update": True,
                "notif_chat_message": True,
                "notif_slack": True
                }
            
            db.session.add(u)
            db.session.commit()

            # Try to fetch user
            u = User.query.get(2)
            assert u.nickname == 'foo'

            # Add a user who doesn't want to be notified
            hashed_password=hashpw("toto1234".encode('utf-8'),gensalt())
            u = User()
            u.nickname="nonotif_user"
            u.password=hashed_password
            u.email="nonotif@ptitoliv.net"
            u.notifications={
                "notif_own_activity" : True,
                "notif_show_add" : True,
                "notif_mark_add": True,
                "notif_homework_add": False,
                "notif_comment_add": True,
                "notif_favorite_update": True,
                "notif_chat_message": True,
                "notif_slack": True
                }

            db.session.add(u)
            db.session.commit()
            
    def test_02_index(self):
        rv = self.client.get('/login')
        assert "Welcome to CineApp" in str(str(rv.data))

    def test_03_login_logout(self):

        # Bad user
        rv=self.client.post('/login',data=dict(username="user",password="pouet"), follow_redirects=True)
        assert "Mauvais utilisateur !" in str(str(rv.data))
        
        # Bad password
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="pouet"), follow_redirects=True)
        assert "Mot de passe incorrect !" in str(str(rv.data))
        
        # Good login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(str(rv.data))
        
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(str(rv.data))
        
        # Login as guest
        rv=self.client.post('/login',data=dict(username="guest",password="guest"), follow_redirects=True)
        assert "Welcome <strong>Guest</strong>" in str(str(rv.data))
        
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(str(rv.data))

    def test_04_add_movie(self):
        with self.app.app_context():
            # Add types
            t = Type()
            t.id="C"
            t.type="Comédie"
            t.show_type = "movie"
            
            db.session.add(t)
            db.session.commit()
            
            # Add origin
            o = Origin()
            o.id="F"
            o.origin="Francais"
            
            db.session.add(o)
            db.session.commit()

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # We are logged => add the movie
        rv=self.client.get('/movie/add')
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajout d'un film" == parsed_html.find(id="add_wizard_label").text

        # --- Edge case: movie with invalid release_date format in search results (L102-105) ---
        from cineapp.tmvdb import tmvdb_connect as orig_tmvdb_connect_date
        def tmvdb_connect_bad_date(url):
            result = orig_tmvdb_connect_date(url)
            if result and 'release_date' in result:
                result['release_date'] = '2024'
            return result
        with patch('cineapp.tmvdb.tmvdb_connect', side_effect=tmvdb_connect_bad_date):
            rv=self.client.post('/movie/add/select',data=dict(search="Titanic",submit_search=True))
            assert "2024" in rv.data.decode("utf-8")

        # --- Edge case: tmvdb_connect returns None inside search_shows (L60) ---
        from cineapp.tmvdb import tmvdb_connect as original_tmvdb_connect
        calls = [0]
        def tmvdb_connect_fail_on_search(url):
            calls[0] += 1
            if calls[0] <= 1:
                return original_tmvdb_connect(url)
            return None
        with patch('cineapp.tmvdb.tmvdb_connect', side_effect=tmvdb_connect_fail_on_search):
            rv=self.client.post('/movie/add/select',data=dict(search="Les Tuche",submit_search=True),follow_redirects=True)
            assert u"Aucun résultat" in rv.data.decode("utf-8")

        # Send the form without any title
        rv=self.client.post('/movie/add/select',data=dict(submit_search=True),follow_redirects=True)
        assert u"Veuillez saisir une recherche" in rv.data.decode("utf-8")

        # Send the form without a incorrect title
        rv=self.client.post('/movie/add/select',data=dict(search="fejsgjsgjsd",submit_search=True),follow_redirects=True)
        assert u"Aucun résultat" in rv.data.decode("utf-8")

        # Fill the movie title
        rv=self.client.post('/movie/add/select',data=dict(search="Les Tuche",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        
        # Let's find the show in the list
        list_shows=(parsed_html.table.find_all('label'))
        found=False
        for cur_show in list_shows:
            if "Les Tuche" in cur_show.text:
                found=True
                break

        assert found==True
        
        # Select the show
        rv=self.client.post('/movie/add/confirm',data=dict(show="66129",submit_select=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajouter le film" == parsed_html.find(id="submit_confirm")['value']
        
        # Store the movie into database
        rv=self.client.post('/movie/add/confirm',data=dict(show_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        list_messages=parsed_html.find_all("div", {"class": "msg-alert"})

        found=False
        for cur_msg in list_messages:
            if "Film ajouté" in cur_msg.text:
                found=True
                break
        assert found==True

        found=False
        for cur_msg in list_messages:
            if "Affiche téléchargée" in cur_msg.text:
                found=True
                break

        # --- Edge case: access select page without search query in session ---
        with self.client.session_transaction() as sess:
            sess.pop('query_show', None)
        rv=self.client.get('/movie/add/select/1', follow_redirects=True)
        assert "Absence de chaine de recherche" in rv.data.decode("utf-8")

        # --- Edge case: invalid page number ---
        rv=self.client.post('/movie/add/select',data=dict(search="Les Tuche",submit_search=True))
        assert rv.status_code == 200
        rv=self.client.get('/movie/add/select/9999', follow_redirects=True)
        assert "Page de resultat inexistante" in rv.data.decode("utf-8")

        # --- Edge case: tmvdb_connect HTTPError during search (L24-25) ---
        with patch('cineapp.tmvdb.urlopen', side_effect=urllib.error.HTTPError(None, 500, 'Internal Server Error', {}, None)):
            rv=self.client.post('/movie/add/select',data=dict(search="Rambo",submit_search=True),follow_redirects=True)
            assert u"Page de resultat inexistante" in rv.data.decode("utf-8")

        # --- Edge case: download_poster fails during add (L39-40) ---
        rv=self.client.post('/movie/add/select',data=dict(search="Zorro",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=(parsed_html.table.find_all('label'))
        igdb_id_zorro=None
        for cur_show in list_shows:
            if "Zorro" in cur_show.text:
                radio = cur_show.find_previous('input', {'type': 'radio'})
                if radio:
                    igdb_id_zorro = radio['value']
                break
        assert igdb_id_zorro is not None

        original_urlopen = urlopen
        def urlopen_fail_on_poster(url, *args, **kwargs):
            if 'w185' in str(url):
                raise Exception("Connection timeout")
            return original_urlopen(url, *args, **kwargs)

        with patch('cineapp.tmvdb.urlopen', side_effect=urlopen_fail_on_poster):
            rv=self.client.post('/movie/add/confirm',data=dict(show_id=igdb_id_zorro,origin="F",type="C",submit_confirm=True),follow_redirects=True)
            assert u"Impossible de télécharger le poster" in rv.data.decode("utf-8")

        # --- Edge case: get_show with invalid TMDB id (L81-82) ---
        rv=self.client.post('/movie/add/confirm',data=dict(show_id="9999999",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        assert u"Impossible de récupérer les informations" in rv.data.decode("utf-8")

        # --- Edge case: movie with empty release_date (L119) ---
        rv=self.client.post('/movie/add/select',data=dict(search="Volte-Face",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=(parsed_html.table.find_all('label'))
        igdb_id_volte=None
        for cur_show in list_shows:
            if "Volte" in cur_show.text:
                radio = cur_show.find_previous('input', {'type': 'radio'})
                if radio:
                    igdb_id_volte = radio['value']
                break
        assert igdb_id_volte is not None

        from cineapp.tmvdb import tmvdb_connect as orig_tmvdb_connect
        def tmvdb_connect_empty_date_no_director(url):
            result = orig_tmvdb_connect(url)
            if result and 'release_date' in result:
                result['release_date'] = ''
            if result and 'credits' in result:
                result['credits']['crew'] = []
            return result
        with patch('cineapp.tmvdb.tmvdb_connect', side_effect=tmvdb_connect_empty_date_no_director):
            rv=self.client.post('/movie/add/confirm',data=dict(show_id=igdb_id_volte,origin="F",type="C",submit_confirm=True),follow_redirects=True)

        with self.app.app_context():
            movie_volte = Movie.query.filter(Movie.name.like('%Volte%')).first()
            assert movie_volte is not None
            assert "Volte" in movie_volte.name
            assert movie_volte.release_date is None
            assert movie_volte.director == "Inconnu"

        # --- Edge case: add a movie with poster download failure (line 243) ---
        with patch('cineapp.shows.get_show') as mock_get_show:
            mock_movie = Movie()
            mock_movie.name = "Test No Poster"
            mock_movie.original_name = "Test No Poster"
            mock_movie.director = "Test Director"
            mock_movie.release_date = datetime(2020, 1, 1)
            mock_movie.overview = "Test overview"
            mock_movie.duration = 120
            mock_movie.external_id = 999999
            mock_movie.poster_path = None
            mock_get_show.return_value = mock_movie

            rv=self.client.post('/movie/add/confirm',data=dict(show_id="999999",origin="F",type="C",submit_confirm=True),follow_redirects=True)
            assert "Impossible de télécharger le poster" in rv.data.decode("utf-8")

        # --- Edge case: add a movie that already exists => IntegrityError (lines 258-262) ---
        # Film "Les Tuche" (TMDB 66129) is already in DB, adding it again triggers unique constraint on external_id
        rv=self.client.post('/movie/add/confirm',data=dict(show_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        assert "déjà existant" in rv.data.decode("utf-8")

        # --- Edge case: POST confirm without any form submitted (L379) ---
        rv=self.client.post('/movie/add/confirm',data=dict(),follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajout d'un film" == parsed_html.find(id="add_wizard_label").text

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_04_update_movie(self):

        """
            Update show feature test
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # --- Edge case: POST update without valid form data ---
        rv=self.client.post('/movie/update',data=dict(),follow_redirects=True)
        assert "Erreur" in rv.data.decode("utf-8")

        # We are logged => load the movie to update
        rv=self.client.get('/movie/display/1',follow_redirects=True)
        assert "Les Tuche" in rv.data.decode("utf-8")

        rv=self.client.post('/movie/update',data=dict(show_id=1,submit_update_show=True),follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Mise à jour du film Les Tuche" == parsed_html.find(id="add_wizard_label").text

        # Send the form without any title
        rv=self.client.post('/movie/update/select',data=dict(submit_search=True),follow_redirects=True)
        assert u"Veuillez saisir une recherche" in rv.data.decode("utf-8")

        # Send the form without a incorrect title
        rv=self.client.post('/movie/update/select',data=dict(search="fejsgjsgjsd",submit_search=True),follow_redirects=True)
        assert u"Aucun résultat" in rv.data.decode("utf-8")
        
        # Fill the movie title
        rv=self.client.post('/movie/update/select',data=dict(search="Les Tuche",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        
        # Let's find the show in the list
        list_shows=(parsed_html.table.find_all('label'))
        found=False
        for cur_show in list_shows:
            if "Les Tuche" in cur_show.text:
                found=True
                break

        assert found==True
        
        # Select the show
        rv=self.client.post('/movie/update/confirm',data=dict(show="66129",submit_select=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Mettre à jour le film" in parsed_html.find(id="submit_confirm")['value']
        
        # Store the movie into database
        rv=self.client.post('/movie/update/confirm',data=dict(show_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        list_messages=parsed_html.find_all("div", {"class": "msg-alert"})

        found=False
        for cur_msg in list_messages:
            if "Film correctement mis à jour" in cur_msg.text:
                found=True
                break
        assert found==True

        found=False
        for cur_msg in list_messages:
            if "Affiche téléchargée" in cur_msg.text:
                found=True
                break

        # --- Edge case: update confirm with show_id missing from session (select step, lines 188-189) ---
        rv=self.client.post('/movie/update/select',data=dict(search="Les Tuche",submit_search=True))
        assert rv.status_code == 200
        with self.client.session_transaction() as sess:
            sess.pop('show_id', None)
        rv=self.client.post('/movie/update/confirm',data=dict(show="66129",submit_select=True),follow_redirects=True)
        assert "Erreur" in rv.data.decode("utf-8")

        # --- Edge case: update confirm with show_id missing from session (confirm step, lines 270-271) ---
        with self.client.session_transaction() as sess:
            sess.pop('show_id', None)
        rv=self.client.post('/movie/update/confirm',data=dict(show_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        assert "Erreur" in rv.data.decode("utf-8")

        # --- Edge case: update confirm with invalid show_id in session (lines 279-280) ---
        with self.client.session_transaction() as sess:
            sess['show_id'] = 99999
        rv=self.client.post('/movie/update/confirm',data=dict(show_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        assert "Erreur" in rv.data.decode("utf-8")

        # --- Edge case: update with poster download failure (line 339) ---
        with patch('cineapp.shows.get_show') as mock_get_show:
            mock_movie = Movie()
            mock_movie.name = "Test No Poster"
            mock_movie.original_name = "Test No Poster"
            mock_movie.director = "Test Director"
            mock_movie.release_date = datetime(2020, 1, 1)
            mock_movie.overview = "Test overview"
            mock_movie.duration = 120
            mock_movie.external_id = 66129
            mock_movie.poster_path = None
            mock_movie.url = "https://www.themoviedb.org/movie/66129"
            mock_get_show.return_value = mock_movie

            rv=self.client.post('/movie/update',data=dict(show_id=1,submit_update_show=True),follow_redirects=True)
            rv=self.client.post('/movie/update/select',data=dict(search="Les Tuche",submit_search=True))
            rv=self.client.post('/movie/update/confirm',data=dict(show="66129",submit_select=True))
            rv=self.client.post('/movie/update/confirm',data=dict(show_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
            assert "Impossible de télécharger le poster" in rv.data.decode("utf-8")

        # Restore the movie with correct data (re-update without mock)
        rv=self.client.post('/movie/update',data=dict(show_id=1,submit_update_show=True),follow_redirects=True)
        rv=self.client.post('/movie/update/select',data=dict(search="Les Tuche",submit_search=True))
        rv=self.client.post('/movie/update/confirm',data=dict(show="66129",submit_select=True))
        rv=self.client.post('/movie/update/confirm',data=dict(show_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        assert "Film correctement mis à jour" in rv.data.decode("utf-8")

        # --- Edge case: IntegrityError during update (lines 374-380) ---
        # Update movie id=2 (Test No Poster) using the TMDB id of movie id=1 (Les Tuche = 66129)
        # This triggers a unique constraint violation on external_id
        rv=self.client.post('/movie/update',data=dict(show_id=2,submit_update_show=True),follow_redirects=True)
        rv=self.client.post('/movie/update/select',data=dict(search="Les Tuche",submit_search=True))
        rv=self.client.post('/movie/update/confirm',data=dict(show="66129",submit_select=True))
        rv=self.client.post('/movie/update/confirm',data=dict(show_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        assert "déjà existant" in rv.data.decode("utf-8")

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_05_edit_profile(self):

        # Fetch the user in order to fill the form with the current notifications parameters
        # Otherwise, when we post that form, all notifications are set to false
        with self.app.app_context():
            u=User.query.get(1);
        
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # Check if we can display the page
        rv=self.client.get('/my/profile', follow_redirects=True)
        assert "Informations Utilisateur" in rv.data.decode('utf-8')

        # In order to repeat the same code for testing all cases for avatar,
        # let's use a dictionnary with a loop. test_avatar.png is used twice in
        # order to test the old avatar deletion code. That code tests also the
        # profile update
        avatar_tests={  "test_avatar.png" : "Avatar correctement mis à jour",
                        "test_avatar2.png" : "Avatar correctement mis à jour",
                        "test_avatar3.xlsx" : "Extension d&#39;image incorrecte",
                        "test_avatar4.png": "Impossible de redimensionner l&#39;image"
                      }

        # Do the update twice in order to test the old avatar deletion
        for avatar, message in avatar_tests.items():

            # Change the avatar
            avatar_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                "ressources/%s" % avatar)
            
            with open(avatar_path, 'rb') as img1:
                    img1BytesIO = io.BytesIO(img1.read())

            rv=self.client.post('/my/profile',
                                 content_type='multipart/form-data',
                                 data=dict(email="ptitoliv+test@ptitoliv.net",upload_avatar=(img1BytesIO,
                                                                                             avatar),
                                 notif_own_activity=u.notifications["notif_own_activity"],
                                 notif_show_add=u.notifications["notif_show_add"],
                                 notif_homework_add=u.notifications["notif_homework_add"],
                                 notif_mark_add=u.notifications["notif_mark_add"],
                                 notif_comment_add=u.notifications["notif_comment_add"],
                                 notif_favorite_update=u.notifications["notif_favorite_update"],
                                 notif_chat_message=u.notifications["notif_chat_message"],
                                 notif_slack=u.notifications["notif_slack"]), follow_redirects=True)
           
            # If we use that file, that message must be displayed
            if avatar == "test_avatar.png":
                assert "Informations mises à jour" in rv.data.decode("utf-8")
            assert message in rv.data.decode("utf-8")

        # Force os.rename to fail after the PNG was saved so that the
        # cleanup branch in resize_avatar (os.remove of the temp .png) runs.
        avatar_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ressources/test_avatar.png")
        with open(avatar_path, 'rb') as img1:
            img1BytesIO = io.BytesIO(img1.read())
        with patch('cineapp.utils.os.rename', side_effect=OSError("rename failed")):
            rv=self.client.post('/my/profile',
                                content_type='multipart/form-data',
                                data=dict(email="ptitoliv+test@ptitoliv.net",upload_avatar=(img1BytesIO, "test_avatar.png"),
                                notif_own_activity=u.notifications["notif_own_activity"],
                                notif_show_add=u.notifications["notif_show_add"],
                                notif_homework_add=u.notifications["notif_homework_add"],
                                notif_mark_add=u.notifications["notif_mark_add"],
                                notif_comment_add=u.notifications["notif_comment_add"],
                                notif_favorite_update=u.notifications["notif_favorite_update"],
                                notif_chat_message=u.notifications["notif_chat_message"],
                                notif_slack=u.notifications["notif_slack"]), follow_redirects=True)
            assert "Impossible de redimensionner l&#39;image" in rv.data.decode("utf-8")

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_05_change_password(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # Let's change the password in a bad way
        rv=self.client.post('/my/password',data=dict(password="toto1234",confirm="toto1235"), follow_redirects=True)
        assert "Les mots de passe ne correspondent pas" in rv.data.decode('utf-8')

        # Let's change the password for real
        rv=self.client.post('/my/password',data=dict(password="toto1234",confirm="toto1234"), follow_redirects=True)
        assert "Mot de passe mis à jour" in rv.data.decode('utf-8')

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_06_mark_movie(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # --- Edge case: mark with non-numeric value (L74-75) ---
        rv=self.client.post('/movie/mark/1',data=dict(mark="abc",comment="cool",seen_where="C",submit_mark=1),follow_redirects=True)
        assert "Pas un chiffre" in rv.data.decode("utf-8")

        # --- Edge case: mark with value > 20 (L77) ---
        rv=self.client.post('/movie/mark/1',data=dict(mark=25,comment="cool",seen_where="C",submit_mark=1),follow_redirects=True)
        assert "Note Incorrecte" in rv.data.decode("utf-8")

        # We are logged => mark the movie
        rv=self.client.post('/movie/mark/1',data=dict(mark=10,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note ajout" in str(rv.data)
        
        # We are logged => mark the movie
        rv=self.client.post('/movie/mark/1',data=dict(mark=16,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note mise" in str(rv.data)

        # --- Edge case: GET mark page for already marked show (L709-710) ---
        rv=self.client.get('/movie/mark/1',follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert "Les Tuche" in parsed_html.find("h1",{"class":"title_position"}).text
     
        # --- Edge case: mail notification failure (L678) ---
        with patch('cineapp.shows.mark_show_notification') as mock_notif:
            mock_notif.return_value = -1
            rv=self.client.post('/movie/mark/1',data=dict(mark=16,comment="cool",seen_where="C",submit_mark=1),follow_redirects=True)
            assert "Impossible d&#39;envoyer la note par mail" in rv.data.decode("utf-8")

        # --- Edge case: IntegrityError on mark commit (L692-695) ---
        with patch('cineapp.shows.db.session.commit') as mock_commit:
            mock_commit.side_effect = IntegrityError("", "", Exception())
            rv=self.client.post('/movie/mark/1',data=dict(mark=16,comment="cool",seen_where="C",submit_mark=1),follow_redirects=True)
            assert "Impossible de noter le film" in rv.data.decode("utf-8")

        # --- Edge case: FlushError on mark commit (L697-700) ---
        with patch('cineapp.shows.db.session.commit') as mock_commit:
            mock_commit.side_effect = FlushError("flush error")
            rv=self.client.post('/movie/mark/1',data=dict(mark=16,comment="cool",seen_where="C",submit_mark=1),follow_redirects=True)
            assert "Impossible de noter le film" in rv.data.decode("utf-8")

        # --- Edge case: mark form validation failure (missing required fields) ---
        rv=self.client.post('/movie/mark/1',data=dict(submit_mark=1),follow_redirects=True)
        assert "has-error" in rv.data.decode("utf-8")

        # --- Publish mark on Slack ---
        rv=self.client.get('/movie/mark/publish/1', follow_redirects=True)
        assert "Slack" in rv.data.decode("utf-8")

        # --- Publish mark with Slack disabled ---
        temp_slack_token=self.app.config["SLACK_TOKEN"]
        self.app.config["SLACK_TOKEN"]=None
        rv=self.client.get('/movie/mark/publish/1', follow_redirects=True)
        assert "désactivées" in rv.data.decode("utf-8")
        self.app.config["SLACK_TOKEN"]=temp_slack_token

        # --- Enable notif_slack via profile edit ---
        rv=self.client.post('/my/profile',data=dict(
            email="ptitoliv@ptitoliv.net",
            notif_slack=True,
            submit_user=True
        ),follow_redirects=True)
        assert rv.status_code == 200

        # --- Mark with Slack notification (bad token → API error, lines 686-689) ---
        temp_slack_token=self.app.config["SLACK_TOKEN"]
        self.app.config["SLACK_TOKEN"]="xoxp-bad-token"

        rv=self.client.post('/movie/mark/1',data=dict(mark=16,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Impossible" in rv.data.decode("utf-8")

        # --- Publish mark with bad token (line 1071) ---
        rv=self.client.get('/movie/mark/publish/1', follow_redirects=True)
        assert "Impossible" in rv.data.decode("utf-8")

        # --- Mark with Slack token None (slack_result == -1, line 687) ---
        self.app.config["SLACK_TOKEN"]=None
        rv=self.client.post('/movie/mark/1',data=dict(mark=16,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "désactivées" in rv.data.decode("utf-8")

        # Restore token
        self.app.config["SLACK_TOKEN"]=temp_slack_token

        # --- Disable notif_slack via profile edit ---
        rv=self.client.post('/my/profile',data=dict(
            email="ptitoliv@ptitoliv.net",
            submit_user=True
        ),follow_redirects=True)
        assert rv.status_code == 200

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_07_comment_mark(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Try to send an empty comment
        rv=self.client.post('/json/add_mark_comment',data=dict(show_id=1,dest_user=1,comment=""),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["error"] == "Vous ne pouvez pas insérer un commentaire vide"

        # Comment the movie
        rv=self.client.post('/json/add_mark_comment',data=dict(show_id=1,dest_user=1,comment="plop"),follow_redirects=True)
        rv=self.client.get('/movie/display/1', follow_redirects=True)
        assert "plop" in str(rv.data)

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

        # User "foo" comments on ptitoliv's mark so commenter != mark owner
        # (covers emails.py own_mark_user=False branch).
        rv=self.client.post('/login',data=dict(username="foo",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>foo</strong>" in str(rv.data)

        rv=self.client.post('/json/add_mark_comment',data=dict(show_id=1,dest_user=1,comment="commented by foo"),follow_redirects=True)
        rv=self.client.get('/movie/display/1', follow_redirects=True)
        assert "commented by foo" in str(rv.data)

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_08_random_movie(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.client.get('/movie/display/random', follow_redirects=True)
        assert "Fiche" in str(rv.data) 
        
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_09_search_movie(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.client.get('/movie/list', follow_redirects=True)
        assert "Liste des films" in str(rv.data)
        
        args = {'search': {'regex': False, 'value': ''}, 'draw': 1, 'start': 0, 'length': 100, 'order': [{'column': 0, 'dir': 'asc'}], 'columns': [{'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'name', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'director', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'average', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_fav', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_mark', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_when', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.3', 'name': '', 'searchable': True}]}
        
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert "Les Tuche" in response_args[0]["name"]

        # --- DataTable: no order directive ---
        args_no_order = dict(args)
        args_no_order['order'] = []
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_no_order)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0

        # --- DataTable: sort by name desc ---
        args_name_desc = dict(args)
        args_name_desc['order'] = [{'column': 0, 'dir': 'desc'}]
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_name_desc)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- DataTable: sort by average desc ---
        args_avg_desc = dict(args)
        args_avg_desc['order'] = [{'column': 2, 'dir': 'desc'}]
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_avg_desc)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- DataTable: sort by average asc ---
        args_avg_asc = dict(args)
        args_avg_asc['order'] = [{'column': 2, 'dir': 'asc'}]
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_avg_asc)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- DataTable: sort by my_mark ---
        args_my_mark = dict(args)
        args_my_mark['order'] = [{'column': 4, 'dir': 'asc'}]
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_my_mark)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- DataTable: sort by my_when ---
        args_my_when = dict(args)
        args_my_when['order'] = [{'column': 5, 'dir': 'asc'}]
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_my_when)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- DataTable: sort by my_fav ---
        args_my_fav = dict(args)
        args_my_fav['order'] = [{'column': 3, 'dir': 'asc'}]
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_my_fav)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- DataTable: sort by other_marks.2 ---
        args_other_marks = dict(args)
        args_other_marks['order'] = [{'column': 10, 'dir': 'asc'}]
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_other_marks)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- DataTable: sort by other_when.2 ---
        args_other_when = dict(args)
        args_other_when['order'] = [{'column': 11, 'dir': 'asc'}]
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_other_when)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- DataTable: sort by other_favs.2 ---
        args_other_favs = dict(args)
        args_other_favs['order'] = [{'column': 9, 'dir': 'asc'}]
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_other_favs)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: text search via search form ---
        rv=self.client.post('/filter',data=dict(search="Tuche",submit_search=True),follow_redirects=True)
        assert rv.status_code == 200
        # Fetch datatable in text search mode
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0

        # --- Filter: text search + sort by average ---
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_avg_desc)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: text search + sort by my_mark (filter_user + text search) ---
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_my_mark)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: origin/type ---
        rv=self.client.post('/filter',data=dict(submit_filter=True,origin="F",type="C"),follow_redirects=True)
        assert rv.status_code == 200
        # Fetch datatable in filter_origin_type mode
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: origin/type + sort by average ---
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_avg_desc)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: origin/type + sort by average asc ---
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_avg_asc)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: origin/type + sort by my_mark (filter_user + filter_origin_type) ---
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_my_mark)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: seen_where ---
        rv=self.client.post('/filter',data=dict(submit_filter=True,where=1),follow_redirects=True)
        assert rv.status_code == 200
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: seen_where + sort by my_mark ---
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_my_mark)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: favorite ---
        # First set a favorite
        rv=self.client.post('/json/favshow/set/1/1',data=dict({'star_type': 'favorite_star'}),follow_redirects=True)
        response_fav=json.loads(rv.data)
        assert response_fav["status"] == "success"

        rv=self.client.post('/filter',data=dict(submit_filter=True,favorite=1),follow_redirects=True)
        assert rv.status_code == 200
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: favorite + sort by my_fav ---
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_my_fav)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # Clean up favorite
        rv=self.client.get('/json/favshow/delete/1/1',follow_redirects=True)

        # --- Reload list with session dict (filter still active) ---
        rv=self.client.post('/filter',data=dict(submit_filter=True,origin="F"),follow_redirects=True)
        rv=self.client.get('/movie/list', follow_redirects=True)
        assert rv.status_code == 200

        # --- Filter: all filters empty (L542) ---
        rv=self.client.post('/filter',data=dict(submit_filter=True),follow_redirects=True)
        assert rv.status_code == 200

        # --- Reload list with full filter dict (L578, 585, 590, 595) ---
        # Set a filter with type, where and favorite (but no origin) to cover all reconstruction branches
        rv=self.client.post('/filter',data=dict(submit_filter=True,type="C",where=1,favorite=1),follow_redirects=True)
        assert rv.status_code == 200
        # GET the list to trigger form reconstruction from session dict
        rv=self.client.get('/movie/list', follow_redirects=True)
        assert rv.status_code == 200

        # --- Reset list ---
        rv=self.client.get('/reset', follow_redirects=True)
        assert rv.status_code == 200

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_10_edit_mark_movie(self):

        with self.app.app_context():

            # Add additional favorites in order to tests specific failure cases (Remove comment of another user)
            mark_comment=MarkComment(user_id=2,mark_user_id=1,mark_show_id=1,posted_when=datetime.now(),message="COMMENT")
            db.session.add(mark_comment)
            db.session.commit()

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.client.post('/json/edit_mark_comment',data=dict(comment_id=1,comment_text="plup"),follow_redirects=True)
        rv=self.client.get('/movie/display/1', follow_redirects=True)
        assert "plup" in str(rv.data) 
        
        # Delete the comment    
        rv=self.client.post('/json/delete_mark_comment',data=dict(comment_id=1),follow_redirects=True)
        rv=self.client.get('/movie/display/1', follow_redirects=True)
        assert "plup" not in str(rv.data) 

        # Delete again the comment
        rv=self.client.post('/json/delete_mark_comment',data=dict(comment_id=1),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["error"] == "Commentaire inexistant ou déjà supprimé"

        # Delete a comment of another user
        rv=self.client.post('/json/delete_mark_comment',data=dict(comment_id=2),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["error"] == "Vous ne pouvez supprimer que vos propres commentaires"
        
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_11_slack_fail_cases(self):

        # Let's try to send a slack notification which is going to fail because we don't have Slack Token

        # First : a notification without configured token
        temp_slack_token=self.app.config["SLACK_TOKEN"]
        self.app.config["SLACK_TOKEN"]=None
        assert slack.slack_mark_notification(None,self.app,"movie") == -1
        self.app.config["SLACK_TOKEN"]=temp_slack_token

        # Then, A notification with a bad channel configured
        slack_channel = slack.SlackChannel(self.app.config["SLACK_TOKEN"],"achannelthatdoesentexist")

        # Syntex tip : https://ongspxm.gitlab.io/blog/2016/11/assertraises-testing-for-errors-in-unittest/
        with self.assertRaises(SystemError):slack_channel.send_message("ZBRAH")

        # Let's do the same but with the slack_mark_notification method (In order to catch the exception)
        assert slack.slack_mark_notification(None,self.app,"movie") == 1

    def test_12_add_tvshow(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => add the movie
        rv=self.client.get('/tvshow/add')
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajout d'une série" == parsed_html.find(id="add_wizard_label").text
        
        # Fill the show title
        rv=self.client.post('/tvshow/add/select',data=dict(search="Babylon 5",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        
        # Let's find the show in the list
        list_shows=(parsed_html.table.find_all('label'))
        found=False
        for cur_show in list_shows:
            if "Babylon 5" in cur_show.text:
                found=True
                break

        assert found==True
        
        # Select the show
        rv=self.client.post('/tvshow/add/confirm',data=dict(show="3137",submit_select=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajouter la série" == parsed_html.find(id="submit_confirm")['value']
        
        # Store the movie into database
        rv=self.client.post('/tvshow/add/confirm',data=dict(show_id="3137",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        list_messages=parsed_html.find_all("div", {"class": "msg-alert"})

        found=False
        for cur_msg in list_messages:
            if "Série ajoutée" in cur_msg.text:
                found=True
                break
        assert found==True

        found=False
        for cur_msg in list_messages:
            if "Affiche téléchargée" in cur_msg.text:
                found=True
                break

        # --- Edge case: tvshow with no showrunner and unknown production status (L155, L160-161) ---
        rv=self.client.post('/tvshow/add/select',data=dict(search="Westworld",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=(parsed_html.table.find_all('label'))
        igdb_id_westworld=None
        for cur_show in list_shows:
            if "Westworld" in cur_show.text:
                radio = cur_show.find_previous('input', {'type': 'radio'})
                if radio:
                    igdb_id_westworld = radio['value']
                break
        assert igdb_id_westworld is not None

        from cineapp.tmvdb import tmvdb_connect as orig_tmvdb_connect_tv
        def tmvdb_connect_no_showrunner(url):
            result = orig_tmvdb_connect_tv(url)
            if result and 'created_by' in result:
                result['created_by'] = []
            if result and 'status' in result:
                result['status'] = 'Fake Unknown Status'
            return result
        with patch('cineapp.tmvdb.tmvdb_connect', side_effect=tmvdb_connect_no_showrunner):
            rv=self.client.post('/tvshow/add/confirm',data=dict(show_id=igdb_id_westworld,origin="F",type="C",submit_confirm=True),follow_redirects=True)

        with self.app.app_context():
            tvshow_ww = TVShow.query.filter(TVShow.name.like('%Westworld%')).first()
            assert tvshow_ww is not None
            assert "Westworld" in tvshow_ww.name
            assert tvshow_ww.director == "Inconnu"
            assert tvshow_ww.production_status is None

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_12_update_tvshow(self):

        """
            Update tvshow feature test
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to tvshow mode
        rv=self.client.get('/switch/tvshow', follow_redirects=True)

        # We are logged => load the tvshow to update
        rv=self.client.get('/tvshow/display/6',follow_redirects=True)
        assert "Babylon 5" in rv.data.decode("utf-8")

        rv=self.client.post('/tvshow/update',data=dict(show_id=6,submit_update_show=True),follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Mise à jour de la série Babylon 5" in parsed_html.find(id="add_wizard_label").text

        # Send the form without any title
        rv=self.client.post('/tvshow/update/select',data=dict(submit_search=True),follow_redirects=True)
        assert u"Veuillez saisir une recherche" in rv.data.decode("utf-8")

        # Fill the tvshow title
        rv=self.client.post('/tvshow/update/select',data=dict(search="Babylon 5",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        # Let's find the show in the list
        list_shows=(parsed_html.table.find_all('label'))
        found=False
        for cur_show in list_shows:
            if "Babylon 5" in cur_show.text:
                found=True
                break

        assert found==True

        # Select the show
        rv=self.client.post('/tvshow/update/confirm',data=dict(show="3137",submit_select=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Mettre à jour la série" in parsed_html.find(id="submit_confirm")['value']

        # Store the tvshow into database
        rv=self.client.post('/tvshow/update/confirm',data=dict(show_id="3137",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        list_messages=parsed_html.find_all("div", {"class": "msg-alert"})

        found=False
        for cur_msg in list_messages:
            if "Série correctement mise à jour" in cur_msg.text:
                found=True
                break
        assert found==True

        found=False
        for cur_msg in list_messages:
            if "Affiche téléchargée" in cur_msg.text:
                found=True
                break

        # --- Edge case: POST update without valid form data ---
        rv=self.client.post('/tvshow/update',data=dict(),follow_redirects=True)
        assert "Erreur" in rv.data.decode("utf-8")

        # --- Edge case: DB error during tvshow dynamic fields sync (L457-459) ---
        with patch('cineapp.shows.db.session.commit', side_effect=Exception("DB sync error")):
            rv=self.client.get('/tvshow/display/6',follow_redirects=True)
            assert rv.status_code == 200
            assert "Babylon 5" in rv.data.decode("utf-8")
            assert "Impossible de synchroniser les données de la série" in rv.data.decode("utf-8")

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_13_mark_tvshow(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # We are logged => mark the show
        rv=self.client.post('/tvshow/mark/6',data=dict(mark=10,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note ajout" in str(rv.data)

        # We are logged => mark the show
        rv=self.client.post('/tvshow/mark/6',data=dict(mark=16,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note mise" in str(rv.data)

        # --- List tvshows and datatable tests ---
        rv=self.client.get('/tvshow/list', follow_redirects=True)
        assert "Liste des séries" in rv.data.decode('utf-8')

        args = {'search': {'regex': False, 'value': ''}, 'draw': 1, 'start': 0, 'length': 100, 'order': [{'column': 0, 'dir': 'asc'}], 'columns': [{'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'name', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'director', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'average', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_fav', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_mark', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_when', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.3', 'name': '', 'searchable': True}]}

        rv=self.client.post('/tvshow/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0
        assert "Babylon 5" in response_args[0]["name"]

        # --- Filter: origin/type in tvshow mode + sort by my_mark (L776-778) ---
        rv=self.client.post('/filter',data=dict(submit_filter=True,origin="F",type="C"),follow_redirects=True)
        assert rv.status_code == 200
        args_my_mark = dict(args)
        args_my_mark['order'] = [{'column': 4, 'dir': 'asc'}]
        rv=self.client.post('/tvshow/json', data=dict(args=json.dumps(args_my_mark)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0
        assert "Babylon 5" in response_args[0]["name"]

        # --- Filter: text search in tvshow mode (L903-904) ---
        rv=self.client.post('/filter',data=dict(search="Babylon",submit_search=True),follow_redirects=True)
        assert rv.status_code == 200
        rv=self.client.post('/tvshow/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0
        assert "Babylon 5" in response_args[0]["name"]

        # --- Reset list ---
        rv=self.client.get('/reset', follow_redirects=True)
        assert rv.status_code == 200

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_14_comment_mark(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => comment the mark
        rv=self.client.post('/json/add_mark_comment',data=dict(show_id=6,dest_user=1,comment="plop"),follow_redirects=True)
        rv=self.client.get('/tvshow/display/6', follow_redirects=True)
        assert "plop" in str(rv.data)

        # --- TVShow dynamic fields sync: force nb_seasons difference to trigger TMDB sync ---
        with self.app.app_context():
            tvshow = TVShow.query.get(6)
            tvshow.nb_seasons = 0
            db.session.commit()
        rv=self.client.get('/tvshow/display/6', follow_redirects=True)
        assert rv.status_code == 200

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_15_random_show(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        rv=self.client.get('/tvshow/display/random', follow_redirects=True)
        assert "Fiche" in str(rv.data)

        # Try random on videogame mode on an empty list (no videogame exists yet)
        rv=self.client.get('/switch/videogame', follow_redirects=True)
        rv=self.client.get('/videogame/display/random', follow_redirects=True)
        assert "Pas de contenu disponible" in rv.data.decode('utf-8')

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_16_switch(self):

        """
            This test tries to switch between different mode
        """

        modes={ 'movie': 'films', 'tvshow': 'séries', 'videogame': 'jeux vidéo' };

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # Switch between availables modes
        for key, value in modes.items():
    
            # Let's change mode
            rv=self.client.get('/switch/%s' % key, follow_redirects=True)
            assert ("Liste des %s" % value) in rv.data.decode('utf-8')

        # Test an unkown category
        rv=self.client.get('/switch/unkown')
        assert rv.status_code == 404

        # Test a direct acccess to an unkown category
        rv=self.client.get('/unkown/list')
        assert rv.status_code == 404

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_17_add_user(self):

        """
            User add test
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # First test ==> Add successfully a user
        rv=self.client.post('/users/add', data=dict(username="toto",email="toto@toto.com",password="toto",confirm="toto"))
        assert "Utilisateur ajouté" in rv.data.decode('utf-8')

        # Second test ==> Try to add the same user
        rv=self.client.post('/users/add', data=dict(username="toto",email="toto@toto.com",password="toto",confirm="toto"))
        assert "déjà existant" in rv.data.decode("utf-8")

        # Third test ==> Test form validation (Empty form)
        rv=self.client.post('/users/add', data=dict())
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        for cur_field in [ "div_username", "div_email", "div_password", "div_confirm" ]:
            assert u"Ce champ est requis" in parsed_html.find(id=cur_field).text

        # Fourth test ==> Field validation
        rv=self.client.post('/users/add', data=dict(username="tutu",email="tutu",password="1224",confirm="tata"))
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        test_fields={ 'div_email': 'Adresse E-Mail Incorrecte', 
            'div_password': 'Les mots de passe ne correspondent pas',
            'div_confirm': 'Les mots de passe ne correspondent pas' 
            }

        for key, value in test_fields.items():
            assert value in parsed_html.find(id=key).text

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_18_guest_mode(self):

        """
            Test app in guest mode
        """
        # Login
        rv=self.client.post('/login',data=dict(username="guest",password="guest"), follow_redirects=True)
        assert "Welcome <strong>Guest</strong>" in str(rv.data) 

        rv=self.client.post('/filter',data=dict(search="Les Tuche",submit_search=True),follow_redirects=True)   
        assert "Recherche Personnalisée: Les Tuche" in rv.data.decode('utf-8')

        args = {'search': {'regex': False, 'value': ''}, 'draw': 1, 'start': 0, 'length': 100, 'order': [{'column': 0, 'dir': 'asc'}], 'columns': [{'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'name', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'director', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'average', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_fav', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_mark', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_when', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.3', 'name': '', 'searchable': True}]}
        
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert "Les Tuche" in response_args[0]["name"]

        # Test that guest control is working trying to access a forbidden page
        rv=self.client.get('/movie/add', follow_redirects=True)
        assert "Accès interdit pour les invités" in rv.data.decode('utf-8')

        # Guest switching show_type redirects to the shows list (views.py:109)
        rv=self.client.get('/switch/tvshow', follow_redirects=True)
        assert "Liste des séries" in rv.data.decode('utf-8')
        # Switch back to movie so we don't leak state to later tests
        rv=self.client.get('/switch/movie', follow_redirects=True)
        assert "Liste des films" in rv.data.decode('utf-8')

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_19_homework(self):

        """
            Display activity flow and data 
        """

        with self.app.app_context():

            # Add additionl data in order to test that we can't remove an homework 
            # given by another user
            movie=Movie(name="Movie",original_name="Original Movie", release_date="2000-01-01", origin="F", director="A guy", duration=142)
            mark=Mark(user_id=1,show_id=8,homework_who=2,homework_when=datetime.now())
            db.session.add(movie)
            db.session.add(mark)
            db.session.commit()

            # Add a movie already with a mark
            mark=Mark(user_id=2,show_id=8,homework_who=1,homework_when=datetime.now(),mark=14,seen_where="C",seen_when=datetime.now())
            db.session.add(movie)
            db.session.add(mark)
            db.session.commit()

            # Fetch the user id for later
            nonotif_user=User.query.filter_by(nickname="nonotif_user").one()

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # Give an homework from user 1 to user 2
        with mail.record_messages() as outbox:
            rv=self.client.get('/homework/add/1/2',follow_redirects=True)
            assert "Devoir ajouté" in rv.data.decode('utf-8')
            assert "Attribution d'un devoir" in outbox[0].subject

        # Fetch the datatable while the homework exists to cover homework_who_user.nickname (L992)
        args = {'search': {'regex': False, 'value': ''}, 'draw': 1, 'start': 0, 'length': 100, 'order': [{'column': 0, 'dir': 'asc'}], 'columns': [{'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'name', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'director', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'average', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_fav', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_mark', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_when', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.3', 'name': '', 'searchable': True}]}
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200
        response_args=json.loads(rv.data)["data"]
        # Find "Les Tuche" (show_id=1) and check that user 2's homework has been assigned by ptitoliv
        entry = [e for e in response_args if "Les Tuche" in e["name"]][0]
        assert entry["other_homework_when"]["2"]["who"] == "ptitoliv"

        # Give an homework from user 1 to user 2 for a show already with a mark
        with mail.record_messages() as outbox:
            rv=self.client.get('/homework/add/8/2',follow_redirects=True)
            assert "Impossible de créer le devoir. Une note existe déjà" in rv.data.decode('utf-8')

        # List homeworks
        rv=self.client.get('/homework/list', follow_redirects=True)
        assert "Liste des devoirs" in rv.data.decode('utf-8')
        assert "A guy" in rv.data.decode('utf-8')

        # List filtered homeworks
        rv=self.client.post('/homework/list', data=dict(from_user_filter=1,to_user_filter=2),follow_redirects=True)
        assert "Liste des devoirs" in rv.data.decode('utf-8')
        assert "Les Tuche" in rv.data.decode('utf-8')

        # Give an incorrect homework
        rv=self.client.get('/homework/add/8/10',follow_redirects=True)
        assert "Impossible de créer le devoir" in rv.data.decode('utf-8')

        # Delete an homework
        with mail.record_messages() as outbox:
            rv=self.client.get('/homework/delete/1/2',follow_redirects=True)
            assert "Devoir annulé" in rv.data.decode('utf-8')
            assert "Annulation d'un devoir" in outbox[0].subject

        # Delete an incorrect homework
        rv=self.client.get('/homework/delete/8/10',follow_redirects=True)
        assert "Ce devoir n&#39;existe pas" in rv.data.decode('utf-8')

        # Delete an unauthorized homework
        rv=self.client.get('/homework/delete/8/1',follow_redirects=True)
        assert "Vous n&#39;avez pas le droit de supprimer ce devoir" in rv.data.decode('utf-8')

        # Delete an homework already with a mark
        with mail.record_messages() as outbox:
            rv=self.client.get('/homework/delete/8/2',follow_redirects=True)
            assert "Impossible de supprimer le devoir - Une note existe déjà" in rv.data.decode('utf-8')

        # Add and remove an homework for a user who doesn't want notification
        rv=self.client.get('/homework/add/1/%s' % nonotif_user.id,follow_redirects=True)
        assert "Devoir ajouté" in rv.data.decode('utf-8')
        assert "Aucune notification à envoyer" in rv.data.decode('utf-8')

        rv=self.client.get('/homework/delete/1/%s' % nonotif_user.id,follow_redirects=True)
        assert "Devoir annulé" in rv.data.decode('utf-8')
        assert "Aucune notification à envoyer" in rv.data.decode('utf-8')

        # --- Homework completion: give movie homework to toto (user 4) then complete it ---
        rv=self.client.get('/homework/add/1/4',follow_redirects=True)
        assert "Devoir ajouté" in rv.data.decode('utf-8')

        rv=self.client.get('/logout', follow_redirects=True)
        rv=self.client.post('/login',data=dict(username="toto",password="toto"), follow_redirects=True)
        assert "Welcome <strong>toto</strong>" in str(rv.data)

        # Complete the homework by marking the show
        rv=self.client.post('/movie/mark/1',data=dict(mark=12,comment="devoir fait",seen_where="M",seen_when="2026-03-28",submit_mark=1),follow_redirects=True)
        assert "Devoir rempli" in rv.data.decode('utf-8')

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_20_favorites(self):

        """
            Test favorite feature
        """

        with self.app.app_context():

            # Add additional favorites in order to tests specific failure cases (Remove favorite for another user)
            favorite_show=FavoriteShow(show_id=1,user_id=2,star_type="favorite_star",added_when=datetime.now())
            db.session.add(favorite_show)
            db.session.commit()

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # Add a show as favorite
        rv=self.client.post('/json/favshow/set/1/1',data=dict({'star_type': 'favorite_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Change the favorite type
        rv=self.client.post('/json/favshow/set/1/1',data=dict({'star_type': 'mustsee_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Change the favorite type but with an incorrect one
        rv=self.client.post('/json/favshow/set/1/1',data=dict({'star_type': 'bad_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "danger"

        # Try to add a forbidden favortie
        rv=self.client.post('/json/favshow/set/1/42',data=dict({'star_type': 'favorite_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "danger"
        assert "Vous n'êtes pas autorisé à ajouter ce film en favori pour cet utilisateur" in response_args["message"]

        # Try to add a favorite on an unknown show
        rv=self.client.post('/json/favshow/set/42/1',data=dict({'star_type': 'favorite_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert "Le film n\'existe pas" in response_args["message"]

        # Try to delete an incorrect favortie
        rv=self.client.get('/json/favshow/delete/42/1',follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "danger"
        assert "Favori inexistant" in response_args["message"]

        # Try to delete an unauthorized favortie
        rv=self.client.get('/json/favshow/delete/1/2',follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "danger"
        assert "Vous n'êtes pas autorisé à supprimer ce film en favori pour cet utilisateur" in response_args["message"]

        # Finally delete a correct favorite
        rv=self.client.get('/json/favshow/delete/1/1',follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_21_activity_flow(self):

        """
            Display activity flow and data 
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # Check if the activity flow route is working
        modes={ 'tvshow': 'séries', 'movie': 'films' };

        # Switch between availables modes
        for key, value in modes.items():

            # Let's change mode
            rv=self.client.get('/switch/%s' % key, follow_redirects=True)
            rv=self.client.get('/activity/show', follow_redirects=True)
            assert "Flux d&#39;activité des %s" % value in str(rv.data.decode('utf-8'))
        
        # Now test the datatable part
        args={'draw': 1, 'columns': [{'data': 'entry_type', 'name': '', 'searchable': True, 'orderable': False, 'search': {'value': '', 'regex': False, 'fixed': []}}, {'data': None, 'name': '', 'searchable': True, 'orderable': False, 'search': {'value': '', 'regex': False, 'fixed': []}}, {'data': 'entry_text', 'name': '', 'searchable': True, 'orderable': False, 'search': {'value': '', 'regex': False, 'fixed': []}}], 'order': [], 'start': 0, 'length': 100, 'search': {'value': '', 'regex': False, 'fixed': []}}

        rv=self.client.post('/activity/update', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0

        # length == -1 -> default length (covers views.py:226)
        args_no_pagination = dict(args)
        args_no_pagination["length"] = -1
        rv=self.client.post('/activity/update', data=dict(args=json.dumps(args_no_pagination)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_22_graphs_movie_mode(self):

        """
            Test all graph endpoints in movie mode
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to movie mode
        rv=self.client.get('/switch/movie', follow_redirects=True)

        # Test all graph endpoints available in movie mode
        graph_endpoints = {
            '/graph/mark': u"Répartition par note",
            '/graph/mark_percent': u"Répartition par note (en %)",
            '/graph/mark_interval': u"Répartition par intervalle",
            '/graph/type': u"Répartition par type",
            '/graph/origin': u"Répartition par origine",
            '/graph/average_type': u"Moyenne par type",
            '/graph/average_origin': u"Moyenne par origine",
            '/graph/year': u"Répartition par année",
            '/graph/year_theater': u"Films vus au ciné",
            '/graph/average_by_year': u"Moyenne par année",
        }

        for endpoint, expected_title in graph_endpoints.items():
            rv=self.client.get(endpoint)
            assert rv.status_code == 200, "Endpoint %s returned %d" % (endpoint, rv.status_code)
            assert expected_title in rv.data.decode('utf-8'), "Title '%s' not found for endpoint %s" % (expected_title, endpoint)

        # Dashboard JSON graph by year/month
        rv=self.client.post('/graph/json/graph_by_year', data=dict(year=2023, user=1), follow_redirects=True)
        assert rv.status_code == 200
        data=json.loads(rv.data)
        assert "theaters" in data and "others" in data and len(data["others"]) > 0

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_23_graphs_tvshow_mode(self):

        """
            Test all graph endpoints in tvshow mode and verify year_theater is forbidden
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to tvshow mode
        rv=self.client.get('/switch/tvshow', follow_redirects=True)

        # Test all graph endpoints available in tvshow mode
        graph_endpoints = {
            '/graph/mark': u"Répartition par note",
            '/graph/mark_percent': u"Répartition par note (en %)",
            '/graph/mark_interval': u"Répartition par intervalle",
            '/graph/type': u"Répartition par type",
            '/graph/origin': u"Répartition par origine",
            '/graph/average_type': u"Moyenne par type",
            '/graph/average_origin': u"Moyenne par origine",
            '/graph/year': u"Répartition par année",
            '/graph/average_by_year': u"Moyenne par année",
        }

        for endpoint, expected_title in graph_endpoints.items():
            rv=self.client.get(endpoint)
            assert rv.status_code == 200, "Endpoint %s returned %d" % (endpoint, rv.status_code)
            assert expected_title in rv.data.decode('utf-8'), "Title '%s' not found for endpoint %s" % (expected_title, endpoint)

        # year_theater should be forbidden in tvshow mode
        rv=self.client.get('/graph/year_theater')
        assert rv.status_code == 404

         # Switch back to tvshow for the remaining assertion
        rv=self.client.get('/switch/tvshow', follow_redirects=True)

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_24_graphs_check_graph_type(self):

        """
            Test that graph pagination (prev/next) is rendered
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to movie mode
        rv=self.client.get('/switch/movie', follow_redirects=True)

        # Test a middle graph (type) - should have both prev and next titles in the page
        rv=self.client.get('/graph/type')
        page_content = rv.data.decode('utf-8')
        assert rv.status_code == 200
        # The type graph is in the middle so it should have navigation references
        assert u"Répartition par intervalle" in page_content or u"Répartition par origine" in page_content

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_25_add_videogame(self):

        """
            Add videogame feature test
        """

        with self.app.app_context():
            # Add a videogame type (genre)
            t = Type()
            t.id="ACT"
            t.type="Action"
            t.show_type = "videogame"

            db.session.add(t)
            db.session.commit()

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # We are logged => add the videogame
        rv=self.client.get('/videogame/add')
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajout d'un jeu vidéo" == parsed_html.find(id="add_wizard_label").text

        # Send the form without any title
        rv=self.client.post('/videogame/add/select',data=dict(submit_search=True),follow_redirects=True)
        assert u"Veuillez saisir une recherche" in rv.data.decode("utf-8")

        # Send the form with an incorrect title
        rv=self.client.post('/videogame/add/select',data=dict(search="fejsgjsgjsd",submit_search=True),follow_redirects=True)
        assert u"Aucun résultat" in rv.data.decode("utf-8")

        # Fill the videogame title
        rv=self.client.post('/videogame/add/select',data=dict(search="Sonic",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        # --- Edge case: navigate to page 2 (L117: has_prev = True) ---
        rv=self.client.get('/videogame/add/select/2',follow_redirects=True)
        parsed_html_p2=BeautifulSoup(rv.data,"html.parser")
        assert "Page 2" in parsed_html_p2.text

        # Go back to page 1
        rv=self.client.get('/videogame/add/select/1',follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        # Let's find the game in the list
        list_shows=(parsed_html.table.find_all('label'))
        found=False
        igdb_id=None
        for cur_show in list_shows:
            if "Sonic" in cur_show.text:
                found=True
                # Get the radio button value (igdb_id)
                radio = cur_show.find_previous('input', {'type': 'radio'})
                if radio:
                    igdb_id = radio['value']
                break

        assert found==True
        assert igdb_id is not None

        # Submit confirm without selecting a game => should redirect back to select page
        rv=self.client.post('/videogame/add/confirm',data=dict(submit_select=True),follow_redirects=True)
        assert "submit_select" in rv.data.decode("utf-8")

        # Select the game
        rv=self.client.post('/videogame/add/confirm',data=dict(show=igdb_id,submit_select=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajouter le jeu vidéo" == parsed_html.find(id="submit_confirm")['value']

        # Store the videogame into database
        rv=self.client.post('/videogame/add/confirm',data=dict(show_id=igdb_id,origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        list_messages=parsed_html.find_all("div", {"class": "msg-alert"})

        found=False
        for cur_msg in list_messages:
            if "Jeu vidéo ajouté" in cur_msg.text:
                found=True
                break
        assert found==True

        # Verify the videogame is in the database
        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first()
            assert videogame is not None
            assert videogame.platforms is not None
            assert videogame.external_id is not None
            assert videogame.overview is not None and videogame.overview != ""

        # --- IGDB: search with missing credentials ---
        from cineapp.igdb import _wrapper_cache
        temp_client_id = self.app.config["IGDB_CLIENT_ID"]
        temp_client_secret = self.app.config["IGDB_CLIENT_SECRET"]
        self.app.config["IGDB_CLIENT_ID"] = ""
        self.app.config["IGDB_CLIENT_SECRET"] = ""
        _wrapper_cache["wrapper"] = None
        _wrapper_cache["expires_at"] = 0

        rv=self.client.post('/videogame/add/select',data=dict(search="Sonic",submit_search=True),follow_redirects=True)
        assert u"Aucun résultat" in rv.data.decode("utf-8")

        # --- IGDB: search with bad credentials (L39-40) ---
        self.app.config["IGDB_CLIENT_ID"] = "bad_client_id"
        self.app.config["IGDB_CLIENT_SECRET"] = "bad_client_secret"

        rv=self.client.post('/videogame/add/select',data=dict(search="Sonic",submit_search=True),follow_redirects=True)
        assert u"Aucun résultat" in rv.data.decode("utf-8")

        self.app.config["IGDB_CLIENT_ID"] = temp_client_id
        self.app.config["IGDB_CLIENT_SECRET"] = temp_client_secret
        _wrapper_cache["wrapper"] = None
        _wrapper_cache["expires_at"] = 0

        # --- IGDB: rate limit error 429 (L63-64) ---
        with patch('cineapp.igdb.IGDBWrapper.api_request', side_effect=requests.HTTPError("429 Too Many Requests")):
            rv=self.client.post('/videogame/add/select',data=dict(search="Sonic",submit_search=True),follow_redirects=True)
            assert u"Aucun résultat" in rv.data.decode("utf-8")

        # --- IGDB: generic exception (L66-68) ---
        with patch('cineapp.igdb.IGDBWrapper.api_request', side_effect=Exception("Connection reset")):
            rv=self.client.post('/videogame/add/select',data=dict(search="Sonic",submit_search=True),follow_redirects=True)
            assert u"Aucun résultat" in rv.data.decode("utf-8")

        # --- DeepL: add videogame with missing API key ---
        temp_deepl_key = self.app.config["DEEPL_API_KEY"]
        self.app.config["DEEPL_API_KEY"] = "incorrect-key"

        # Search a game different from Sonic
        rv=self.client.post('/videogame/add/select',data=dict(search="Zelda",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=(parsed_html.table.find_all('label'))
        igdb_id_zelda=None
        for cur_show in list_shows:
            if "Zelda" in cur_show.text:
                radio = cur_show.find_previous('input', {'type': 'radio'})
                if radio:
                    igdb_id_zelda = radio['value']
                break
        assert igdb_id_zelda is not None

        # Confirm without DeepL => flash warning about translation
        rv=self.client.post('/videogame/add/confirm',data=dict(show_id=igdb_id_zelda,origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
        assert u"Impossible de traduire le résumé" in rv.data.decode("utf-8")

        self.app.config["DEEPL_API_KEY"] = temp_deepl_key

        # --- download_poster: HTTP error 404 (L262) ---
        rv=self.client.post('/videogame/add/select',data=dict(search="Mario",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=(parsed_html.table.find_all('label'))
        igdb_id_mario=None
        for cur_show in list_shows:
            if "Mario" in cur_show.text:
                radio = cur_show.find_previous('input', {'type': 'radio'})
                if radio:
                    igdb_id_mario = radio['value']
                break
        assert igdb_id_mario is not None

        mock_response = type('MockResponse', (), {'status_code': 404})()
        with patch('cineapp.igdb.requests.get', return_value=mock_response):
            rv=self.client.post('/videogame/add/confirm',data=dict(show_id=igdb_id_mario,origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
            assert u"Impossible de télécharger le poster" in rv.data.decode("utf-8")

        # --- download_poster: network exception (L269-271) ---
        rv=self.client.post('/videogame/add/select',data=dict(search="Tetris",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=(parsed_html.table.find_all('label'))
        igdb_id_tetris=None
        for cur_show in list_shows:
            if "Tetris" in cur_show.text:
                radio = cur_show.find_previous('input', {'type': 'radio'})
                if radio:
                    igdb_id_tetris = radio['value']
                break
        assert igdb_id_tetris is not None

        with patch('cineapp.igdb.requests.get', side_effect=Exception("Connection timeout")):
            rv=self.client.post('/videogame/add/confirm',data=dict(show_id=igdb_id_tetris,origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
            assert u"Impossible de télécharger le poster" in rv.data.decode("utf-8")

        # --- get_game: invalid date + no developer/publisher (L183-184, L214, L216) ---
        fake_game = [{
            "id": 99999,
            "name": "Fake Game",
            "first_release_date": -99999999999,
            "summary": "A fake game"
        }]
        with patch('cineapp.igdb._igdb_request', return_value=fake_game):
            # First do a search to populate the session with the fake game
            rv=self.client.post('/videogame/add/select',data=dict(search="Fake",submit_search=True))
            # Then select the game to trigger get_game
            rv=self.client.post('/videogame/add/confirm',data=dict(show=99999,submit_select=True),follow_redirects=True)
            assert "Fake Game" in rv.data.decode("utf-8")

        # --- get_game: IGDB API returns no results on confirm (L173-174) ---
        rv=self.client.post('/videogame/add/select',data=dict(search="Metroid",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=(parsed_html.table.find_all('label'))
        igdb_id_metroid=None
        for cur_show in list_shows:
            if "Metroid" in cur_show.text:
                radio = cur_show.find_previous('input', {'type': 'radio'})
                if radio:
                    igdb_id_metroid = radio['value']
                break
        assert igdb_id_metroid is not None

        with patch('cineapp.igdb._igdb_request', return_value=None):
            rv=self.client.post('/videogame/add/confirm',data=dict(show_id=igdb_id_metroid,origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
            assert u"Impossible de récupérer les informations" in rv.data.decode("utf-8")

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_26_update_videogame(self):

        """
            Update videogame feature test
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Find the videogame id
        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first()
            videogame_id = videogame.id
            videogame_igdb_id = videogame.external_id

        # We are logged => load the videogame to update
        rv=self.client.get('/videogame/display/%s' % videogame_id, follow_redirects=True)
        assert "Sonic" in rv.data.decode("utf-8")

        rv=self.client.post('/videogame/update',data=dict(show_id=videogame_id,submit_update_show=True),follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Mise à jour du jeu vidéo" in parsed_html.find(id="add_wizard_label").text

        # Send the form without any title
        rv=self.client.post('/videogame/update/select',data=dict(submit_search=True),follow_redirects=True)
        assert u"Veuillez saisir une recherche" in rv.data.decode("utf-8")

        # Fill the videogame title
        rv=self.client.post('/videogame/update/select',data=dict(search="Sonic",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        # Let's find the game in the list
        list_shows=(parsed_html.table.find_all('label'))
        found=False
        igdb_id=None
        for cur_show in list_shows:
            if "Sonic" in cur_show.text:
                found=True
                radio = cur_show.find_previous('input', {'type': 'radio'})
                if radio:
                    igdb_id = radio['value']
                break

        assert found==True

        # Submit confirm without selecting a game => should redirect back to select page
        rv=self.client.post('/videogame/update/confirm',data=dict(submit_select=True),follow_redirects=False)
        assert rv.status_code == 302

        # Select the game
        rv=self.client.post('/videogame/update/confirm',data=dict(show=igdb_id,submit_select=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Mettre à jour le jeu vidéo" in parsed_html.find(id="submit_confirm")['value']

        # Store the videogame into database
        rv=self.client.post('/videogame/update/confirm',data=dict(show_id=igdb_id,origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        list_messages=parsed_html.find_all("div", {"class": "msg-alert"})

        found=False
        for cur_msg in list_messages:
            if "Jeu vidéo correctement mis à jour" in cur_msg.text:
                found=True
                break
        assert found==True

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_27_mark_videogame(self):

        """
            Mark videogame feature test
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Find the videogame id
        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first()
            videogame_id = videogame.id

        # We are logged => mark the videogame
        rv=self.client.post('/videogame/mark/%s' % videogame_id,data=dict(mark=18,comment="chef d'oeuvre",seen_where="M",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note ajout" in str(rv.data)

        # Update the mark
        rv=self.client.post('/videogame/mark/%s' % videogame_id,data=dict(mark=19,comment="encore mieux",seen_where="M",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note mise" in str(rv.data)

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_28_comment_mark_videogame(self):

        """
            Comment a videogame mark
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Find the videogame id
        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first()
            videogame_id = videogame.id

        # Comment the videogame mark
        rv=self.client.post('/json/add_mark_comment',data=dict(show_id=videogame_id,dest_user=1,comment="super jeu"),follow_redirects=True)
        rv=self.client.get('/videogame/display/%s' % videogame_id, follow_redirects=True)
        assert "super jeu" in str(rv.data)

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_29_display_videogame(self):

        """
            Display videogame and check videogame-specific fields
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Find the videogame id
        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first()
            videogame_id = videogame.id

        # Display the videogame
        rv=self.client.get('/videogame/display/%s' % videogame_id, follow_redirects=True)
        page_content = rv.data.decode('utf-8')
        assert "Sonic" in page_content

        # Check videogame-specific labels
        assert u"Développeur(s)" in page_content or "veloppeur" in page_content

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_30_random_videogame(self):

        """
            Random videogame feature test
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        rv=self.client.get('/videogame/display/random', follow_redirects=True)
        assert "Fiche" in str(rv.data)

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_31_search_videogame(self):

        """
            Search/list videogame feature test
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # --- Set comment to None directly in DB to cover L951 ---
        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first()
            videogame_id = videogame.id
            mark = Mark.query.get((1, videogame_id))
            mark.comment = None
            db.session.commit()

        # We are logged => list videogames
        rv=self.client.get('/videogame/list', follow_redirects=True)
        assert "Liste des jeux" in rv.data.decode('utf-8')

        args = {'search': {'regex': False, 'value': ''}, 'draw': 1, 'start': 0, 'length': 100, 'order': [{'column': 0, 'dir': 'asc'}], 'columns': [{'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'name', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'director', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'average', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_fav', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_mark', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_when', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.3', 'name': '', 'searchable': True}]}

        rv=self.client.post('/videogame/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)

        response_args=json.loads(rv.data)["data"]
        assert "Sonic" in response_args[0]["name"]

        # --- Filter: origin/type in videogame mode + sort by my_mark (L779-781) ---
        rv=self.client.post('/filter',data=dict(submit_filter=True,origin="F",type="ACT"),follow_redirects=True)
        assert rv.status_code == 200
        args_my_mark = dict(args)
        args_my_mark['order'] = [{'column': 4, 'dir': 'asc'}]
        rv=self.client.post('/videogame/json', data=dict(args=json.dumps(args_my_mark)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0
        assert "Sonic" in response_args[0]["name"]

        # --- Filter: text search in videogame mode (L905-906) ---
        rv=self.client.post('/filter',data=dict(search="Sonic",submit_search=True),follow_redirects=True)
        assert rv.status_code == 200
        rv=self.client.post('/videogame/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0
        assert "Sonic" in response_args[0]["name"]

        # --- Filter: text search + sort by average asc (L912) ---
        args_avg_asc = dict(args)
        args_avg_asc['order'] = [{'column': 2, 'dir': 'asc'}]
        rv=self.client.post('/videogame/json', data=dict(args=json.dumps(args_avg_asc)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0

        # --- Reset list ---
        rv=self.client.get('/reset', follow_redirects=True)
        assert rv.status_code == 200

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_32_homework_videogame(self):

        """
            Test homework feature in videogame mode
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Find the videogame id
        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first()
            videogame_id = videogame.id

        # Give a homework from user 1 to user 2
        with mail.record_messages() as outbox:
            rv=self.client.get('/homework/add/%s/2' % videogame_id, follow_redirects=True)
            assert "Devoir ajouté" in rv.data.decode('utf-8')
            assert "Attribution d'un devoir" in outbox[0].subject

        # Delete the homework
        with mail.record_messages() as outbox:
            rv=self.client.get('/homework/delete/%s/2' % videogame_id, follow_redirects=True)
            assert "Devoir annulé" in rv.data.decode('utf-8')
            assert "Annulation d'un devoir" in outbox[0].subject

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_33_favorites_videogame(self):

        """
            Test favorite feature in videogame mode
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Find the videogame id
        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first()
            videogame_id = videogame.id

        # Add a videogame as favorite
        rv=self.client.post('/json/favshow/set/%s/1' % videogame_id,data=dict({'star_type': 'favorite_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Change the favorite type
        rv=self.client.post('/json/favshow/set/%s/1' % videogame_id,data=dict({'star_type': 'mustsee_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Delete the favorite
        rv=self.client.get('/json/favshow/delete/%s/1' % videogame_id, follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_34_activity_flow_videogame(self):

        """
            Display activity flow in videogame mode
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        rv=self.client.get('/activity/show', follow_redirects=True)
        assert "Flux d&#39;activité des jeux vidéo" in rv.data.decode('utf-8')

        # Test the datatable part
        args={'draw': 1, 'columns': [{'data': 'entry_type', 'name': '', 'searchable': True, 'orderable': False, 'search': {'value': '', 'regex': False, 'fixed': []}}, {'data': None, 'name': '', 'searchable': True, 'orderable': False, 'search': {'value': '', 'regex': False, 'fixed': []}}, {'data': 'entry_text', 'name': '', 'searchable': True, 'orderable': False, 'search': {'value': '', 'regex': False, 'fixed': []}}], 'order': [], 'start': 0, 'length': 100, 'search': {'value': '', 'regex': False, 'fixed': []}}

        rv=self.client.post('/activity/update', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_35_graphs_videogame_mode(self):

        """
            Test all graph endpoints in videogame mode
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Test all graph endpoints available in videogame mode
        graph_endpoints = {
            '/graph/mark': u"Répartition par note",
            '/graph/mark_percent': u"Répartition par note (en %)",
            '/graph/mark_interval': u"Répartition par intervalle",
            '/graph/type': u"Répartition par type",
            '/graph/origin': u"Répartition par origine",
            '/graph/average_type': u"Moyenne par type",
            '/graph/average_origin': u"Moyenne par origine",
            '/graph/year': u"Répartition par année",
            '/graph/average_by_year': u"Moyenne par année",
        }

        for endpoint, expected_title in graph_endpoints.items():
            rv=self.client.get(endpoint)
            assert rv.status_code == 200, "Endpoint %s returned %d" % (endpoint, rv.status_code)
            assert expected_title in rv.data.decode('utf-8'), "Title '%s' not found for endpoint %s" % (expected_title, endpoint)

        # year_theater should be forbidden in videogame mode
        rv=self.client.get('/graph/year_theater')
        assert rv.status_code == 404

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_36_push_notifications(self):

        """
            Test push notification subscribe and unsubscribe
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        # Subscribe to push notifications
        subscription_data = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-123",
            "keys": {
                "p256dh": "test-public-key-p256dh",
                "auth": "test-auth-token"
            }
        }
        rv=self.client.post('/notifications/subscribe', data=json.dumps(subscription_data), content_type='application/json')
        response=json.loads(rv.data)
        assert response["status"] == "success"

        # Verify subscription is stored in database
        with self.app.app_context():
            sub = PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/test-endpoint-123").first()
            assert sub is not None
            assert sub.public_key == "test-public-key-p256dh"
            assert sub.auth_token == "test-auth-token"
            assert sub.user_id == 1

        # Logout triggers notification_unsubscribe for all session subscriptions
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

        # Verify subscription has been removed from database
        with self.app.app_context():
            sub = PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/test-endpoint-123").first()
            assert sub is None

        # --- Error case: DB error during subscribe (L30-32) ---
        # Re-login and subscribe once, then subscribe again with a different endpoint
        # The second subscribe will fail because session_id has a unique constraint
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        rv=self.client.post('/notifications/subscribe', data=json.dumps(subscription_data), content_type='application/json')
        response=json.loads(rv.data)
        assert response["status"] == "success"

        subscription_data_duplicate = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-456",
            "keys": {
                "p256dh": "another-public-key",
                "auth": "another-auth-token"
            }
        }
        rv=self.client.post('/notifications/subscribe', data=json.dumps(subscription_data_duplicate), content_type='application/json')
        response=json.loads(rv.data)
        assert response["status"] == "failure"

        # --- Error case: DB error during unsubscribe (L65-67) ---
        with patch('cineapp.push.db.session.commit', side_effect=Exception("DB delete error")):
            rv=self.client.get('/logout', follow_redirects=True)
            assert "Welcome to CineApp" in str(rv.data)

        # Subscription should still be in DB since delete failed
        with self.app.app_context():
            sub = PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/test-endpoint-123").first()
            assert sub is not None

            # Clean up manually
            db.session.delete(sub)
            db.session.commit()

        # --- notification_send: nominal case (L38-48) ---
        with self.app.app_context():
            serialized_subs = [subscription_data]
            with patch('cineapp.push.webpush') as mock_webpush:
                notification_send(serialized_subs, "/chat", "ptitoliv: Hello !")
                mock_webpush.assert_called_once()

        # --- notification_send: WebPushException case (L49-52) ---
        with self.app.app_context():
            with patch('cineapp.push.webpush', side_effect=WebPushException("Push failed")):
                notification_send(serialized_subs, "/chat", "ptitoliv: Hello !")

    def test_37_chat(self):

        """
            Test chat features: page access, SocketIO connection, message sending
        """

        # --- Access chat page (L79) ---
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data)

        rv=self.client.get('/chat')
        assert rv.status_code == 200

        # --- SocketIO: connect and receive history (L84-99, L25-37) ---
        socketio_client = socketio.test_client(self.app, flask_test_client=self.client, namespace='/chat_ws')
        assert socketio_client.is_connected(namespace='/chat_ws')
        received = socketio_client.get_received(namespace='/chat_ws')

        # --- SocketIO: send a message (L106-130, L40-73) ---
        socketio_client.emit('chat_message', {"data": "Hello tout le monde !"}, namespace='/chat_ws')

        received = socketio_client.get_received(namespace='/chat_ws')
        assert len(received) > 0, "No messages received after sending chat message"
        assert received[0]['name'] == 'message'
        assert "Hello tout le monde" in received[0]['args']['msg']
        assert "Aujourd'hui" in received[0]['args']['date']

        # Check message was stored in database
        with self.app.app_context():
            msg = ChatMessage.query.filter_by(message="Hello tout le monde !").first()
            assert msg is not None
            assert msg.user_id == 1

        # --- SocketIO: send a message with @mention (L57-68) ---
        socketio_client.emit('chat_message', {"data": "@foo regarde ce film !"}, namespace='/chat_ws')

        received = socketio_client.get_received(namespace='/chat_ws')
        assert len(received) > 0
        assert "@foo" in received[0]['args']['msg']

        # --- SocketIO: @mention with exception in notification (L65-66) ---
        with patch('cineapp.chat.chat_message_notification', side_effect=Exception("SMTP error")):
            socketio_client.emit('chat_message', {"data": "@foo erreur email !"}, namespace='/chat_ws')

        received = socketio_client.get_received(namespace='/chat_ws')
        assert len(received) > 0
        assert "@foo erreur email" in received[0]['args']['msg']

        # --- SocketIO: old message date formatting (L36-37) ---
        with self.app.app_context():
            old_msg = ChatMessage(message="Vieux message", posted_when=datetime(2020, 1, 1, 12, 0), user_id=1)
            db.session.add(old_msg)
            db.session.commit()

        # Reconnect to trigger history replay with old message
        socketio_client.disconnect(namespace='/chat_ws')
        socketio_client = socketio.test_client(self.app, flask_test_client=self.client, namespace='/chat_ws')
        received = socketio_client.get_received(namespace='/chat_ws')
        has_old_format = any("01/01/2020" in msg['args']['date'] for msg in received if msg['name'] == 'message')
        assert has_old_format

        # --- SocketIO: send empty message (L132-134) ---
        socketio_client.emit('chat_message', {"data": ""}, namespace='/chat_ws')
        received = socketio_client.get_received(namespace='/chat_ws')
        assert len(received) == 0

        # --- SocketIO: push notification via Process fork (L50-51) ---
        with self.app.app_context():
            sub = PushNotification(endpoint_id="https://fcm.googleapis.com/fcm/send/foo-endpoint", public_key="foo-key", auth_token="foo-auth", session_id="foo-session", user_id=2)
            db.session.add(sub)
            db.session.commit()

        socketio_client.get_received(namespace='/chat_ws')
        with patch('cineapp.chat.Process') as mock_process:
            socketio_client.emit('chat_message', {"data": "message avec push"}, namespace='/chat_ws')
            mock_process.return_value.start.assert_called()

        received = socketio_client.get_received(namespace='/chat_ws')
        assert len(received) > 0
        assert "message avec push" in received[0]['args']['msg']

        # Clean up subscription
        with self.app.app_context():
            PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/foo-endpoint").delete()
            db.session.commit()

        # --- SocketIO: IntegrityError on commit (L124-127) ---
        with patch('cineapp.chat.db.session.commit', side_effect=IntegrityError("mock", "mock", Exception("mock"))):
            socketio_client.emit('chat_message', {"data": "message qui plante"}, namespace='/chat_ws')

        received = socketio_client.get_received(namespace='/chat_ws')
        assert len(received) == 0

        # Disconnect and logout
        socketio_client.disconnect(namespace='/chat_ws')

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)
