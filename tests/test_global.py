# -*- coding: utf-8 -*-

from future import standard_library
standard_library.install_aliases()
import os, sys, json, requests, urllib.error
from urllib.request import urlopen
from cineapp import create_app, minutes_to_human_duration, date_format, socketio, slack
from cineapp.utils import html_to_markdown
from cineapp.models import db, User, Type, Origin, Mark, Movie, TVShow, VideoGame, FavoriteShow, MarkComment, PushNotification, ChatMessage
from igdb.wrapper import IGDBWrapper
from cineapp.emails import mail
from cineapp.jinja_testers import is_movie, is_tvshow, is_videogame
from cineapp.push import notification_send
from pywebpush import WebPushException
from datetime import datetime, timedelta
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
        assert "Se connecter" in str(str(rv.data))

    def test_03_login_logout(self):

        # Bad user
        rv=self.client.post('/login',data=dict(username="user",password="pouet"), follow_redirects=True)
        assert "Mauvais utilisateur !" in str(str(rv.data))
        
        # Bad password
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="pouet"), follow_redirects=True)
        assert "Mot de passe incorrect !" in str(str(rv.data))
        
        # Good login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(str(rv.data))
        
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(str(rv.data))
        
        # Login as guest
        rv=self.client.post('/login',data=dict(username="guest",password="guest"), follow_redirects=True)
        assert '<span id="topbar-username">Guest</span>' in str(str(rv.data))

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(str(rv.data))

        # `next` is not honored at all (no open redirect / CWE-601): even a
        # malicious target never takes us off-site — login lands on the dashboard.
        rv=self.client.post('/login?next=http://evil.example/phish',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=False)
        assert "evil.example" not in rv.location
        assert "/dashboard" in rv.location
        rv=self.client.get('/logout', follow_redirects=True)

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
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 

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

        # --- Edge case: a downloaded poster that isn't a valid image (tmvdb.py:41) ---
        from cineapp.tmvdb import download_poster
        with patch('cineapp.tmvdb.urlopen') as mock_urlopen:
            mock_urlopen.return_value.read.return_value = b'this is not an image'
            with self.app.app_context():
                assert download_poster("http://example.test/fake-poster.jpg") is False

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
        list_shows=parsed_html.find_all('label', class_='wizard-result')
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

        list_messages=parsed_html.find_all("div", {"class": "flash"})

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
        rv=self.client.post('/movie/add/select',data=dict(search="Piège de cristal",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        igdb_id_piege=None
        for cur_show in list_shows:
            if "Piège" in cur_show.text:
                radio = cur_show.find('input', {'type': 'radio'})
                if radio:
                    igdb_id_piege = radio['value']
                break
        assert igdb_id_piege is not None

        original_urlopen = urlopen
        def urlopen_fail_on_poster(url, *args, **kwargs):
            if 'w500' in str(url):
                raise Exception("Connection timeout")
            return original_urlopen(url, *args, **kwargs)

        with patch('cineapp.tmvdb.urlopen', side_effect=urlopen_fail_on_poster):
            rv=self.client.post('/movie/add/confirm',data=dict(show_id=igdb_id_piege,origin="F",type="C",submit_confirm=True),follow_redirects=True)
            assert u"Impossible de télécharger le poster" in rv.data.decode("utf-8")

        # --- Edge case: get_show with invalid TMDB id (L81-82) ---
        rv=self.client.post('/movie/add/confirm',data=dict(show_id="9999999",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        assert u"Impossible de récupérer les informations" in rv.data.decode("utf-8")

        # --- Edge case: movie with empty release_date (L119) ---
        rv=self.client.post('/movie/add/select',data=dict(search="Volte-Face",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        igdb_id_volte=None
        for cur_show in list_shows:
            if "Volte" in cur_show.text:
                radio = cur_show.find('input', {'type': 'radio'})
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
        assert "Se connecter" in str(rv.data)

    def test_04_update_movie(self):

        """
            Update show feature test
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        list_shows=parsed_html.find_all('label', class_='wizard-result')
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

        list_messages=parsed_html.find_all("div", {"class": "flash"})

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
        assert "Se connecter" in str(rv.data)

    def test_05_edit_profile(self):

        # Fetch the user in order to fill the form with the current notifications parameters
        # Otherwise, when we post that form, all notifications are set to false
        with self.app.app_context():
            u=User.query.get(1);
        
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 

        # Check if we can display the page
        rv=self.client.get('/my/profile', follow_redirects=True)
        assert "Vos informations" in rv.data.decode('utf-8')

        # In order to repeat the same code for testing all cases for avatar,
        # let's use a dictionnary with a loop. test_avatar.png is used twice in
        # order to test the old avatar deletion code. That code tests also the
        # profile update
        avatar_tests={  "test_avatar.png" : "Avatar correctement mis à jour",
                        "test_avatar2.png" : "Avatar correctement mis à jour",
                        "test_avatar3.xlsx" : "Extension d&#39;image incorrecte",
                        # A non-image file named .png (spoofed type) is now rejected on
                        # real content (Pillow), not on the client Content-Type (M-6).
                        "test_avatar4.png": "Extension d&#39;image incorrecte"
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
        assert "Se connecter" in str(rv.data)

    def test_05_change_password(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 

        # Let's change the password in a bad way
        rv=self.client.post('/my/password',data=dict(password="toto1234",confirm="toto1235"), follow_redirects=True)
        assert "Les mots de passe ne correspondent pas" in rv.data.decode('utf-8')

        # Let's change the password for real
        rv=self.client.post('/my/password',data=dict(password="toto1234",confirm="toto1234"), follow_redirects=True)
        assert "Mot de passe mis à jour" in rv.data.decode('utf-8')

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_06_mark_movie(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 
        
        # --- Publish before any mark exists → flash + redirect, not a raw 404 ---
        rv=self.client.post('/movie/mark/publish/1', follow_redirects=True)
        assert "Aucune note" in rv.data.decode("utf-8")

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

        # --- Stored XSS regression: a malicious comment must be sanitized on
        # write (sanitize_comment) so the display page never renders a script
        # payload, while legitimate CKEditor formatting is preserved ---
        rv=self.client.post('/movie/mark/1',data=dict(mark=16,comment='<p>Bon <strong>film</strong></p><img src=x onerror=alert(1)><script>alert(2)</script>',seen_where="C",submit_mark=1),follow_redirects=True)
        assert "Note mise" in str(rv.data)
        rv=self.client.get('/movie/display/1',follow_redirects=True)
        page=rv.data.decode("utf-8")
        assert "onerror=alert(1)" not in page
        assert "<img src=x" not in page
        assert "<script>alert(2)" not in page
        assert "<strong>film</strong>" in page

        # --- Edge case: GET mark page for already marked show (L709-710) ---
        rv=self.client.get('/movie/mark/1',follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert "Les Tuche" in parsed_html.find("h1",{"class":"title"}).text
     
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
        rv=self.client.post('/movie/mark/publish/1', follow_redirects=True)
        assert "Slack" in rv.data.decode("utf-8")

        # --- Publish mark with Slack disabled ---
        temp_slack_token=self.app.config["SLACK_TOKEN"]
        self.app.config["SLACK_TOKEN"]=None
        rv=self.client.post('/movie/mark/publish/1', follow_redirects=True)
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
        rv=self.client.post('/movie/mark/publish/1', follow_redirects=True)
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
        assert "Se connecter" in str(rv.data)

    def test_07_comment_mark(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

        # Try to send an empty comment
        rv=self.client.post('/json/add_mark_comment',data=dict(show_id=1,dest_user=1,comment=""),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["error"] == "Vous ne pouvez pas insérer un commentaire vide"

        # IDOR: try to comment on a mark that doesn't exist (no Mark(1,999))
        rv=self.client.post('/json/add_mark_comment',data=dict(show_id=999,dest_user=1,comment="injecté"),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["error"] == "La note ciblée n'existe pas"

        # Comment the movie
        rv=self.client.post('/json/add_mark_comment',data=dict(show_id=1,dest_user=1,comment="plop"),follow_redirects=True)
        # The serialized user in the JSON response must never leak the password hash
        assert "password" not in json.loads(rv.data)["user"]
        rv=self.client.get('/movie/display/1', follow_redirects=True)
        assert "plop" in str(rv.data)

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

        # User "foo" comments on ptitoliv's mark so commenter != mark owner
        # (covers emails.py own_mark_user=False branch).
        rv=self.client.post('/login',data=dict(username="foo",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">foo</span>' in str(rv.data)

        rv=self.client.post('/json/add_mark_comment',data=dict(show_id=1,dest_user=1,comment="commented by foo"),follow_redirects=True)
        rv=self.client.get('/movie/display/1', follow_redirects=True)
        assert "commented by foo" in str(rv.data)

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_08_random_movie(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.client.get('/movie/display/random', follow_redirects=True)
        assert "Fiche externe" in str(rv.data) 
        
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_09_search_movie(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 
        
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

        # --- ORDER BY injection guard (I-1): a malicious sort column and
        #     direction are allow-listed back to a safe default → the raw
        #     text(f"{order_column} {order_dir}") fragment stays valid SQL
        #     (no 500), instead of a syntax error / blind injection. ---
        args_inject = dict(args)
        args_inject['order'] = [{'column': 0, 'dir': 'asc; SELECT 1'}]
        args_inject['columns'] = list(args['columns'])
        args_inject['columns'][0] = dict(args['columns'][0], data='name); DROP TABLE movie;--')
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args_inject)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        assert rv.status_code == 200
        assert "data" in json.loads(rv.data)

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
        rv=self.client.post('/json/favshow/set/1',data=dict({'star_type': 'favorite_star'}),follow_redirects=True)
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
        rv=self.client.post('/json/favshow/delete/1',follow_redirects=True)

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
        assert "Se connecter" in str(rv.data)

    def test_10_edit_mark_movie(self):

        with self.app.app_context():

            # Add additional favorites in order to tests specific failure cases (Remove comment of another user)
            mark_comment=MarkComment(user_id=2,mark_user_id=1,mark_show_id=1,posted_when=datetime.now(),message="COMMENT")
            db.session.add(mark_comment)
            db.session.commit()

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 
        
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
        assert "Se connecter" in str(rv.data)

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

        # End-to-end: a CKEditor (HTML) rating comment stored through the real
        # marking endpoint must convert to clean Slack mrkdwn — bold/italic become
        # Slack markers, lists become bullets, no HTML tag leaks. Posting via the
        # route runs sanitize_comment on write exactly like production, and reading
        # the Mark back proves the comment reaches slack_mark_notification as raw
        # HTML (no double conversion): the conversion happens once, in slack.py.
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)
        rv=self.client.post('/movie/mark/1',data=dict(mark=16,comment="<p>Un <strong>bon</strong> film <em>culte</em>.</p><ul><li>Image</li><li>Musique</li></ul>",seen_where="C",submit_mark=1),follow_redirects=True)
        assert "Note mise" in str(rv.data)
        with self.app.app_context():
            stored_comment=Mark.query.get((1,1)).comment
        converted=html_to_markdown(stored_comment)
        assert "<" not in converted
        assert "*bon*" in converted
        assert "_culte_" in converted
        assert "• Image" in converted
        assert "• Musique" in converted
        # None and tag-less legacy comments pass through cleanly.
        assert html_to_markdown(None) == ""
        assert html_to_markdown("Commentaire tout simple.") == "Commentaire tout simple."
        # No stray space between a closing emphasis marker and trailing punctuation
        # ("_sublime_ ," → "_sublime_,"), while correct French spacing before ":" stays.
        assert html_to_markdown("<p>C'est <u>sublime</u>, vraiment <strong>top</strong>.</p>") == "C'est _sublime_, vraiment *top*."
        assert html_to_markdown("<p>Mon <strong>verdict</strong> : oui.</p>") == "Mon *verdict* : oui."

    def test_12_add_tvshow(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 
        
        # We are logged => add the movie
        rv=self.client.get('/tvshow/add')
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajout d'une série" == parsed_html.find(id="add_wizard_label").text
        
        # Fill the show title
        rv=self.client.post('/tvshow/add/select',data=dict(search="Babylon 5",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        
        # Let's find the show in the list
        list_shows=parsed_html.find_all('label', class_='wizard-result')
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

        list_messages=parsed_html.find_all("div", {"class": "flash"})

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
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        igdb_id_westworld=None
        for cur_show in list_shows:
            if "Westworld" in cur_show.text:
                radio = cur_show.find('input', {'type': 'radio'})
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

        # --- Regression: a movie and a TV show may share the same external_id.
        # TheMovieDB uses independent id namespaces for movies and TV shows, so
        # id 95 is BOTH the movie "Armageddon" and the series "Buffy contre les
        # vampires". Adding the series after the movie must NOT trip the
        # uq_shows_external unique key (which now spans show_type) — both rows
        # must persist. Before the fix this second add raised an IntegrityError. ---
        rv=self.client.post('/movie/add/confirm',data=dict(show_id="95",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        assert rv.status_code == 200
        rv=self.client.post('/tvshow/add/confirm',data=dict(show_id="95",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        assert rv.status_code == 200

        with self.app.app_context():
            armageddon = Movie.query.filter_by(external_source="tmvdb", external_id=95).one()
            buffy = TVShow.query.filter_by(external_source="tmvdb", external_id=95).one()
            assert "Armageddon" in armageddon.name
            assert "Buffy" in buffy.name

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_12_update_tvshow(self):

        """
            Update tvshow feature test
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        list_shows=parsed_html.find_all('label', class_='wizard-result')
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

        list_messages=parsed_html.find_all("div", {"class": "flash"})

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
        assert "Se connecter" in str(rv.data)

    def test_13_mark_tvshow(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

        # Re-enable notif_slack (disabled at the end of test_06)
        rv=self.client.post('/my/profile',data=dict(
            email="ptitoliv@ptitoliv.net",
            notif_slack=True,
            submit_user=True
        ),follow_redirects=True)
        assert rv.status_code == 200

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
        assert "Se connecter" in str(rv.data)

    def test_14_comment_mark(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 
        
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
        assert "Se connecter" in str(rv.data)

    def test_15_random_show(self):

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 
        
        rv=self.client.get('/tvshow/display/random', follow_redirects=True)
        assert "Fiche externe" in str(rv.data)

        # Try random on videogame mode on an empty list (no videogame exists yet)
        rv=self.client.get('/switch/videogame', follow_redirects=True)
        rv=self.client.get('/videogame/display/random', follow_redirects=True)
        assert "Pas de contenu disponible" in rv.data.decode('utf-8')

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_16_switch(self):

        """
            This test tries to switch between different mode
        """

        modes={ 'movie': 'films', 'tvshow': 'séries', 'videogame': 'jeux vidéo' };

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 

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
        assert "Se connecter" in str(rv.data)

    def test_17_add_user(self):

        """
            User add test
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 

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
        assert "Se connecter" in str(rv.data)

    def test_18_guest_mode(self):

        """
            Test app in guest mode
        """
        # Login
        rv=self.client.post('/login',data=dict(username="guest",password="guest"), follow_redirects=True)
        assert '<span id="topbar-username">Guest</span>' in str(rv.data) 

        rv=self.client.post('/filter',data=dict(search="Les Tuche",submit_search=True),follow_redirects=True)   
        assert "Recherche Personnalisée: Les Tuche" in rv.data.decode('utf-8')

        args = {'search': {'regex': False, 'value': ''}, 'draw': 1, 'start': 0, 'length': 100, 'order': [{'column': 0, 'dir': 'asc'}], 'columns': [{'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'name', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'director', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'average', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_fav', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_mark', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_when', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.3', 'name': '', 'searchable': True}]}
        
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert "Les Tuche" in response_args[0]["name"]

        # Every @guest_control-protected view must reject a guest with the
        # "Accès interdit" flash. One representative URL per guarded view (the
        # mutating JSON endpoints — favorites/comments — included). Keep this
        # list in sync whenever a @guest_control route is added or removed.
        guarded_routes = [
            ("GET",  "/users/add"),
            ("GET",  "/dashboard"),
            ("GET",  "/activity/show"),
            ("POST", "/activity/update"),
            ("GET",  "/movie/add"),
            ("GET",  "/movie/add/select/1"),
            ("POST", "/movie/add/confirm"),
            ("POST", "/movie/update"),
            ("GET",  "/movie/mark/1"),
            ("POST", "/movie/mark/publish/1"),
            ("POST", "/homework/add/1/2"),
            ("POST", "/homework/delete/1/2"),
            ("GET",  "/homework/list"),
            ("GET",  "/my/profile"),
            ("GET",  "/my/password"),
            ("GET",  "/graph/mark"),
            ("POST", "/graph/json/graph_by_year"),
            ("GET",  "/chat"),
            ("POST", "/json/add_mark_comment"),
            ("POST", "/json/delete_mark_comment"),
            ("POST", "/json/favshow/set/1"),
            ("POST", "/json/favshow/delete/1"),
            ("POST", "/notifications/subscribe"),
        ]
        for method, path in guarded_routes:
            rv = self.client.open(path, method=method, follow_redirects=True)
            assert "Accès interdit pour les invités" in rv.data.decode('utf-8'), \
                "guest_control missing/not blocking on %s %s" % (method, path)

        # A guest must not reach the chat over SocketIO: the connect handler
        # rejects the connection. Use a throwaway flask client so the shared
        # self.client session/state stays clean for the rest of the suite.
        guest_client = self.app.test_client()
        guest_client.post('/login', data=dict(username="guest", password="guest"), follow_redirects=True)
        guest_ws = socketio.test_client(self.app, flask_test_client=guest_client, namespace='/chat_ws')
        assert not guest_ws.is_connected(namespace='/chat_ws')

        # Guest switching show_type redirects to the shows list (views.py:109)
        rv=self.client.get('/switch/tvshow', follow_redirects=True)
        assert "Liste des séries" in rv.data.decode('utf-8')
        # Switch back to movie so we don't leak state to later tests
        rv=self.client.get('/switch/movie', follow_redirects=True)
        assert "Liste des films" in rv.data.decode('utf-8')

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_19_homework(self):

        """
            Display activity flow and data 
        """

        with self.app.app_context():

            # Add additionl data in order to test that we can't remove an homework
            # given by another user. show_id 10 = this "A guy" movie (TheMovieDB
            # collision test in test_12 now adds 2 shows upstream, shifting the id).
            movie=Movie(name="Movie",original_name="Original Movie", release_date="2000-01-01", origin="F", director="A guy", duration=142)
            mark=Mark(user_id=1,show_id=10,homework_who=2,homework_when=datetime.now())
            db.session.add(movie)
            db.session.add(mark)
            db.session.commit()

            # Add a movie already with a mark
            mark=Mark(user_id=2,show_id=10,homework_who=1,homework_when=datetime.now(),mark=14,seen_where="C",seen_when=datetime.now())
            db.session.add(movie)
            db.session.add(mark)
            db.session.commit()

            # Fetch the user id for later
            nonotif_user=User.query.filter_by(nickname="nonotif_user").one()

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 

        # Give an homework from user 1 to user 2
        with mail.record_messages() as outbox:
            rv=self.client.post('/homework/add/1/2',follow_redirects=True)
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
            rv=self.client.post('/homework/add/10/2',follow_redirects=True)
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
        rv=self.client.post('/homework/add/10/10',follow_redirects=True)
        assert "Impossible de créer le devoir" in rv.data.decode('utf-8')

        # Delete an homework
        with mail.record_messages() as outbox:
            rv=self.client.post('/homework/delete/1/2',follow_redirects=True)
            assert "Devoir annulé" in rv.data.decode('utf-8')
            assert "Annulation d'un devoir" in outbox[0].subject

        # Delete an incorrect homework
        rv=self.client.post('/homework/delete/10/10',follow_redirects=True)
        assert "Ce devoir n&#39;existe pas" in rv.data.decode('utf-8')

        # Delete an unauthorized homework
        rv=self.client.post('/homework/delete/10/1',follow_redirects=True)
        assert "Vous n&#39;avez pas le droit de supprimer ce devoir" in rv.data.decode('utf-8')

        # Delete an homework already with a mark
        with mail.record_messages() as outbox:
            rv=self.client.post('/homework/delete/10/2',follow_redirects=True)
            assert "Impossible de supprimer le devoir - Une note existe déjà" in rv.data.decode('utf-8')

        # Add and remove an homework for a user who doesn't want notification
        rv=self.client.post('/homework/add/1/%s' % nonotif_user.id,follow_redirects=True)
        assert "Devoir ajouté" in rv.data.decode('utf-8')
        assert "Aucune notification à envoyer" in rv.data.decode('utf-8')

        rv=self.client.post('/homework/delete/1/%s' % nonotif_user.id,follow_redirects=True)
        assert "Devoir annulé" in rv.data.decode('utf-8')
        assert "Aucune notification à envoyer" in rv.data.decode('utf-8')

        # --- Homework completion: give movie homework to toto (user 4) then complete it ---
        rv=self.client.post('/homework/add/1/4',follow_redirects=True)
        assert "Devoir ajouté" in rv.data.decode('utf-8')

        rv=self.client.get('/logout', follow_redirects=True)
        rv=self.client.post('/login',data=dict(username="toto",password="toto"), follow_redirects=True)
        assert '<span id="topbar-username">toto</span>' in str(rv.data)

        # Complete the homework by marking the show
        rv=self.client.post('/movie/mark/1',data=dict(mark=12,comment="devoir fait",seen_where="M",seen_when="2026-03-28",submit_mark=1),follow_redirects=True)
        assert "Devoir rempli" in rv.data.decode('utf-8')

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

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
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 

        # Add a show as favorite
        rv=self.client.post('/json/favshow/set/1',data=dict({'star_type': 'favorite_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Change the favorite type
        rv=self.client.post('/json/favshow/set/1',data=dict({'star_type': 'mustsee_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Change the favorite type but with an incorrect one
        rv=self.client.post('/json/favshow/set/1',data=dict({'star_type': 'bad_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "danger"

        # Try to add a favorite on an unknown show
        rv=self.client.post('/json/favshow/set/42',data=dict({'star_type': 'favorite_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert "Le film n\'existe pas" in response_args["message"]

        # Try to delete an incorrect favortie
        rv=self.client.post('/json/favshow/delete/42',follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "danger"
        assert "Favori inexistant" in response_args["message"]

        # Finally delete a correct favorite
        rv=self.client.post('/json/favshow/delete/1',follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_21_activity_flow(self):

        """
            Display activity flow and data 
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data) 

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

        # Cover every humanize_when relative-time branch (utils.py) through the
        # real flow: add shows dated at each age, then read them back from
        # /activity/update where the route humanizes show.added_when (movie mode).
        now = datetime.now()
        ages = {
            "humanize-instant": now - timedelta(seconds=5),
            "humanize-minutes": now - timedelta(minutes=12, seconds=30),
            "humanize-hours": now - timedelta(hours=3, minutes=30),
            "humanize-yesterday": now - timedelta(days=1, hours=3),
            "humanize-days": now - timedelta(days=3, hours=3),
            "humanize-months": now - timedelta(days=40),
        }
        with self.app.app_context():
            for name, added in ages.items():
                db.session.add(Movie(name=name, added_when=added, added_by_user=1))
            db.session.commit()

        # Large length so even the oldest entry is in the returned window.
        args_humanize = dict(args)
        args_humanize["length"] = 1000
        rv=self.client.post('/activity/update', data=dict(args=json.dumps(args_humanize)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        whens = [ e["when"] for e in json.loads(rv.data)["data"] if e["action_type"] == "shows" ]
        assert "à l'instant" in whens
        assert "il y a 12min" in whens
        assert "il y a 3h" in whens
        assert any(w.startswith("hier · ") for w in whens)
        assert "il y a 3j" in whens
        assert any("·" in w and "hier" not in w and "il y a" not in w for w in whens)

        # Remove the synthetic shows so they don't skew the later graph/stats tests.
        with self.app.app_context():
            for name in ages:
                db.session.delete(Movie.query.filter_by(name=name).first())
            db.session.commit()

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_22_graphs_movie_mode(self):

        """
            Test all graph endpoints in movie mode
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        assert "Se connecter" in str(rv.data)

    def test_23_graphs_tvshow_mode(self):

        """
            Test all graph endpoints in tvshow mode and verify year_theater is forbidden
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        assert "Se connecter" in str(rv.data)

    def test_24_graphs_check_graph_type(self):

        """
            Test that graph pagination (prev/next) is rendered
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        assert "Se connecter" in str(rv.data)

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
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        rv=self.client.post('/videogame/add/select',data=dict(search="Sonic the Hedgehog",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        # --- Edge case: navigate to page 2 (L117: has_prev = True) ---
        rv=self.client.get('/videogame/add/select/2',follow_redirects=True)
        parsed_html_p2=BeautifulSoup(rv.data,"html.parser")
        assert "Page 2" in parsed_html_p2.text

        # Go back to page 1
        rv=self.client.get('/videogame/add/select/1',follow_redirects=True)
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        # Let's find the game in the list
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        found=False
        igdb_id=None
        for cur_show in list_shows:
            if "Sonic" in cur_show.text:
                found=True
                # Get the radio button value (igdb_id)
                radio = cur_show.find('input', {'type': 'radio'})
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

        list_messages=parsed_html.find_all("div", {"class": "flash"})

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
            assert videogame.external_source == "igdb"
            assert videogame.overview is not None and videogame.overview != ""
            # Sonic has neither a European localized title nor a French alternative
            # name => _pick_display_name falls back to the original name (branch 3).
            assert videogame.name == "Sonic the Hedgehog"
            assert videogame.original_name == "Sonic the Hedgehog"

        # --- Title localization: European localized title wins (branch 1) ---
        # Super Mario Strikers (IGDB id 2256) is titled "Mario Smash Football" in
        # the European localization (region id 4) while its default IGDB name is
        # "Super Mario Strikers".
        rv=self.client.post('/videogame/add/confirm',data=dict(show_id="2256",origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
        assert u"Jeu vidéo ajouté" in rv.data.decode("utf-8")
        with self.app.app_context():
            mario = VideoGame.query.filter_by(external_id=2256, external_source="igdb").first()
            assert mario is not None
            assert mario.name == "Mario Smash Football"
            assert mario.original_name == "Super Mario Strikers"

        # --- Title localization: French alternative name (branch 2) ---
        # Oddworld: Abe's Oddysee (IGDB id 999) has no European localized title but
        # a French alternative name "Oddworld : L'Odyssée d'Abe".
        rv=self.client.post('/videogame/add/confirm',data=dict(show_id="999",origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
        assert u"Jeu vidéo ajouté" in rv.data.decode("utf-8")
        with self.app.app_context():
            oddworld = VideoGame.query.filter_by(external_id=999, external_source="igdb").first()
            assert oddworld is not None
            assert oddworld.name == u"Oddworld : L'Odyssée d'Abe"
            assert oddworld.original_name == u"Oddworld: Abe's Oddysee"

        # --- Composite UNIQUE (external_source, external_id): a videogame may share external_id with a movie ---
        # Les Tuche (TMDB id 66129, external_source='tmvdb') was added in test_03; mock IGDB so the videogame
        # add route receives a game with the same external_id but external_source='igdb'.
        with patch('cineapp.shows.igdb_api.get_game') as mock_get_game:
            fake_vg = VideoGame()
            fake_vg.name = "Fake game sharing id 66129 with Les Tuche"
            fake_vg.original_name = fake_vg.name
            fake_vg.external_id = 66129
            fake_vg.external_source = "igdb"
            fake_vg.url = "https://igdb.com/games/fake-66129"
            fake_vg.director = "Test Studio"
            fake_vg.overview = "Fake overview"
            fake_vg.overview_translated = True
            fake_vg.poster_path = "fake_poster.jpg"
            fake_vg.platforms = "PC"
            fake_vg.publisher = "Test"
            mock_get_game.return_value = (fake_vg, [])

            rv = self.client.post('/videogame/add/confirm',
                data=dict(show_id="66129", origin="F", type="ACT", submit_confirm=True),
                follow_redirects=True)
            assert "Jeu vidéo ajouté" in rv.data.decode("utf-8")

        with self.app.app_context():
            assert Movie.query.filter_by(external_id=66129, external_source="tmvdb").first() is not None
            assert VideoGame.query.filter_by(external_id=66129, external_source="igdb").first() is not None

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

        # --- Add a crafted game through the real add flow so get_game's parsing is
        # exercised on three edge cases at once:
        #   - a release_dates entry with an invalid platform is skipped (igdb.py:142)
        #   - a platform present only in release_dates is appended (igdb.py:167)
        #   - a regional release date with an invalid (None) timestamp falls back to
        #     None instead of crashing (igdb.py:335-336)
        #   - a regional release date whose timestamp is out of datetime range
        #     falls back to None instead of crashing (igdb.py:362-363)
        #   - a cover whose download isn't a valid image is rejected (igdb.py:428)
        # release_region id 9999 matches no region, so the regional-dates loop never
        # dereferences the invalid platform. ---
        crafted_game = {
            "id": 314159,
            "name": "Crafted Platform Game",
            "summary": "A crafted game for platform parsing coverage.",
            "url": "https://www.igdb.com/games/crafted-platform-game",
            "first_release_date": 700000000,
            "cover": {"url": "//images.igdb.com/igdb/image/upload/t_thumb/crafted.jpg"},
            "platforms": [{"name": "Switch"}],
            "release_dates": [
                {"platform": None, "date": 100, "release_region": {"id": 9999}},
                {"platform": {"name": "PC"}, "date": 200, "release_region": {"id": 9999}},
                {"platform": {"name": "PC"}, "date": None, "release_region": {"id": 9999}},
                {"platform": {"name": "PC"}, "date": 10000000000000, "release_region": {"id": 9999}},
            ],
            "alternative_names": [],
            "game_localizations": [],
            "involved_companies": [],
        }
        with patch('cineapp.igdb._igdb_request', return_value=[crafted_game]), \
             patch('cineapp.igdb.requests.get') as mock_poster_get:
            # The cover "download" returns non-image bytes, so download_poster
            # rejects it (igdb.py:428) and the game is stored without a poster.
            mock_poster_get.return_value.status_code = 200
            mock_poster_get.return_value.content = b'not a real image'
            rv=self.client.post('/videogame/add/confirm',data=dict(show_id="314159",origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
            assert "Jeu vidéo ajouté" in rv.data.decode("utf-8")

        with self.app.app_context():
            crafted = VideoGame.query.filter_by(external_id=314159, external_source="igdb").first()
            assert crafted is not None
            # Switch (undated) comes after PC (dated), and PC came only from release_dates.
            assert crafted.platforms == "PC, Switch"
            # The non-image cover was rejected, so no poster was stored.
            assert crafted.poster_path is None

            # Remove the crafted game so later videogame/graph tests are unaffected.
            db.session.delete(crafted)
            db.session.commit()

        # --- DeepL: add videogame with missing API key ---
        temp_deepl_key = self.app.config["DEEPL_API_KEY"]
        self.app.config["DEEPL_API_KEY"] = "incorrect-key"

        # Search a game different from Sonic
        rv=self.client.post('/videogame/add/select',data=dict(search="Zelda",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        igdb_id_zelda=None
        for cur_show in list_shows:
            if "Zelda" in cur_show.text:
                radio = cur_show.find('input', {'type': 'radio'})
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
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        igdb_id_mario=None
        for cur_show in list_shows:
            if "Mario" in cur_show.text:
                radio = cur_show.find('input', {'type': 'radio'})
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
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        igdb_id_tetris=None
        for cur_show in list_shows:
            if "Tetris" in cur_show.text:
                radio = cur_show.find('input', {'type': 'radio'})
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
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        igdb_id_metroid=None
        for cur_show in list_shows:
            if "Metroid" in cur_show.text:
                radio = cur_show.find('input', {'type': 'radio'})
                if radio:
                    igdb_id_metroid = radio['value']
                break
        assert igdb_id_metroid is not None

        with patch('cineapp.igdb._igdb_request', return_value=None):
            rv=self.client.post('/videogame/add/confirm',data=dict(show_id=igdb_id_metroid,origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
            assert u"Impossible de récupérer les informations" in rv.data.decode("utf-8")

        # --- get_game: localization without cover => fallback to global cover ---
        # 13 Sentinels: Aegis Rim has IGDB localizations missing the cover field for some regions
        rv=self.client.post('/videogame/add/select',data=dict(search="13 Sentinels",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        igdb_id_sentinels=None
        for cur_show in list_shows:
            if "13 Sentinels" in cur_show.text:
                radio = cur_show.find('input', {'type': 'radio'})
                if radio:
                    igdb_id_sentinels = radio['value']
                break
        assert igdb_id_sentinels is not None

        rv=self.client.post('/videogame/add/confirm',data=dict(show_id=igdb_id_sentinels,origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
        assert u"Jeu vidéo ajouté" in rv.data.decode("utf-8")

        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%13 Sentinels%')).first()
            assert videogame is not None
            assert videogame.poster_path is not None

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_26_update_videogame(self):

        """
            Update videogame feature test
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        found=False
        igdb_id=None
        for cur_show in list_shows:
            if "Sonic" in cur_show.text:
                found=True
                radio = cur_show.find('input', {'type': 'radio'})
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

        list_messages=parsed_html.find_all("div", {"class": "flash"})

        found=False
        for cur_msg in list_messages:
            if "Jeu vidéo correctement mis à jour" in cur_msg.text:
                found=True
                break
        assert found==True

        # --- Composite UNIQUE on UPDATE: a videogame can be updated to share external_id with a movie ---
        # Add a fake movie via mocked TMDB with a fresh external_id, then update a videogame via mocked
        # IGDB to that same external_id. Different external_source values must allow the pair to coexist.
        rv = self.client.get('/switch/movie', follow_redirects=True)
        with patch('cineapp.shows.get_show') as mock_get_show:
            fake_movie = Movie()
            fake_movie.name = "Fake movie sharing id 77777"
            fake_movie.original_name = fake_movie.name
            fake_movie.director = "Test"
            fake_movie.release_date = datetime(2020, 1, 1)
            fake_movie.overview = "Fake"
            fake_movie.duration = 120
            fake_movie.external_id = 77777
            fake_movie.external_source = "tmvdb"
            fake_movie.poster_path = "fake.jpg"
            fake_movie.url = "https://themoviedb.org/movie/77777"
            mock_get_show.return_value = fake_movie

            rv = self.client.post('/movie/add/confirm',
                data=dict(show_id="77777", origin="F", type="C", submit_confirm=True),
                follow_redirects=True)
            assert "Film ajouté" in rv.data.decode("utf-8")

        rv = self.client.get('/switch/videogame', follow_redirects=True)

        with patch('cineapp.shows.igdb_api.get_game') as mock_get_game:
            fake_vg = VideoGame()
            fake_vg.name = "Sonic remapped to id 77777"
            fake_vg.original_name = fake_vg.name
            fake_vg.external_id = 77777
            fake_vg.external_source = "igdb"
            fake_vg.url = "https://igdb.com/games/77777"
            fake_vg.director = "Sega"
            fake_vg.overview = "Updated"
            fake_vg.overview_translated = True
            fake_vg.poster_path = "fake.jpg"
            fake_vg.platforms = "PC"
            fake_vg.publisher = "Sega"
            mock_get_game.return_value = (fake_vg, [])

            with self.client.session_transaction() as sess:
                sess['show_id'] = videogame_id
                sess['show'] = '77777'
                sess['query_show'] = 'Sonic'

            rv = self.client.post('/videogame/update/confirm',
                data=dict(show_id="77777", origin="F", type="ACT", submit_confirm=True),
                follow_redirects=True)
            assert "Jeu vidéo correctement mis à jour" in rv.data.decode("utf-8")

        with self.app.app_context():
            assert Movie.query.filter_by(external_id=77777, external_source="tmvdb").first() is not None
            updated_vg = VideoGame.query.filter_by(external_id=77777, external_source="igdb").first()
            assert updated_vg is not None
            assert updated_vg.id == videogame_id

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_27_mark_videogame(self):

        """
            Mark videogame feature test
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Find the videogame id
        with self.app.app_context():
            videogame_id = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first().id

        # We are logged => mark the videogame
        rv=self.client.post('/videogame/mark/%s' % videogame_id,data=dict(mark=18,comment="chef d'oeuvre",seen_where="M",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note ajout" in str(rv.data)

        # Update the mark
        rv=self.client.post('/videogame/mark/%s' % videogame_id,data=dict(mark=19,comment="encore mieux",seen_where="M",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note mise" in str(rv.data)

        # --- Slack videogame card coverage (slack.py:53,55,60) ---
        # Mario Smash Football has a release date AND an overview > 300 chars, so
        # its Slack card shows the year and truncates the overview (53, 60). The
        # fake game has no release date, so its card takes the empty-year path (55).
        with self.app.app_context():
            full_game_id = VideoGame.query.filter(VideoGame.name.like('%Mario Smash Football%')).first().id
            nodate_game_id = VideoGame.query.filter(VideoGame.name.like('%Fake game%')).first().id

        rv=self.client.post('/videogame/mark/%s' % full_game_id,data=dict(mark=12,comment="bon jeu",seen_where="M",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note ajout" in str(rv.data)
        rv=self.client.post('/videogame/mark/%s' % nodate_game_id,data=dict(mark=8,comment="sans date",seen_where="M",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note ajout" in str(rv.data)

        # Remove the marks added only for the Slack card coverage.
        with self.app.app_context():
            Mark.query.filter_by(user_id=1, show_id=full_game_id).delete()
            Mark.query.filter_by(user_id=1, show_id=nodate_game_id).delete()
            db.session.commit()

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_28_comment_mark_videogame(self):

        """
            Comment a videogame mark
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        assert "Se connecter" in str(rv.data)

    def test_29_display_videogame(self):

        """
            Display videogame and check videogame-specific fields
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        assert "Se connecter" in str(rv.data)

    def test_30_random_videogame(self):

        """
            Random videogame feature test
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        rv=self.client.get('/videogame/display/random', follow_redirects=True)
        assert "Fiche externe" in str(rv.data)

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_31_search_videogame(self):

        """
            Search/list videogame feature test
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        assert "13 Sentinels" in response_args[0]["name"]

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

        # --- Regression: an FTS query containing an InnoDB stopword ("the") must
        # still return results. Add the real "The Last of Us" through the IGDB
        # search+confirm flow, then search its full title; without stopword
        # filtering the mandatory "+the" matches nothing (the is a default InnoDB
        # stopword) so the search wrongly returned 0 rows. ---
        rv=self.client.post('/videogame/add/select',data=dict(search="The Last of Us",submit_search=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        list_shows=parsed_html.find_all('label', class_='wizard-result')
        igdb_id_tlou=None
        for cur_show in list_shows:
            if "Last of Us" in cur_show.text:
                radio = cur_show.find('input', {'type': 'radio'})
                if radio:
                    igdb_id_tlou = radio['value']
                break
        assert igdb_id_tlou is not None

        rv=self.client.post('/videogame/add/confirm',data=dict(show_id=igdb_id_tlou,origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
        assert "Jeu vidéo ajouté" in rv.data.decode("utf-8")

        with self.app.app_context():
            tlou = VideoGame.query.filter_by(external_id=int(igdb_id_tlou), external_source="igdb").first()
            assert tlou is not None
            tlou_name = tlou.name

        rv=self.client.post('/filter',data=dict(search="The Last of Us",submit_search=True),follow_redirects=True)
        assert rv.status_code == 200
        rv=self.client.post('/videogame/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        names=[r["name"] for r in response_args]
        assert tlou_name in names, \
            "FTS stopword regression: 'The Last of Us' search returned %r" % names

        # Remove the game so later videogame/graph tests are unaffected.
        with self.app.app_context():
            tlou = VideoGame.query.filter_by(external_id=int(igdb_id_tlou), external_source="igdb").first()
            db.session.delete(tlou)
            db.session.commit()

        # --- Reset list ---
        rv=self.client.get('/reset', follow_redirects=True)
        assert rv.status_code == 200

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_32_homework_videogame(self):

        """
            Test homework feature in videogame mode
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Find the videogame id
        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first()
            videogame_id = videogame.id

        # Give a homework from user 1 to user 2
        with mail.record_messages() as outbox:
            rv=self.client.post('/homework/add/%s/2' % videogame_id, follow_redirects=True)
            assert "Devoir ajouté" in rv.data.decode('utf-8')
            assert "Attribution d'un devoir" in outbox[0].subject

        # Delete the homework
        with mail.record_messages() as outbox:
            rv=self.client.post('/homework/delete/%s/2' % videogame_id, follow_redirects=True)
            assert "Devoir annulé" in rv.data.decode('utf-8')
            assert "Annulation d'un devoir" in outbox[0].subject

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_33_favorites_videogame(self):

        """
            Test favorite feature in videogame mode
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Find the videogame id
        with self.app.app_context():
            videogame = VideoGame.query.filter(VideoGame.name.like('%Sonic%')).first()
            videogame_id = videogame.id

        # Add a videogame as favorite
        rv=self.client.post('/json/favshow/set/%s' % videogame_id,data=dict({'star_type': 'favorite_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Change the favorite type
        rv=self.client.post('/json/favshow/set/%s' % videogame_id,data=dict({'star_type': 'mustsee_star'}),follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Delete the favorite
        rv=self.client.post('/json/favshow/delete/%s' % videogame_id, follow_redirects=True)
        response_args=json.loads(rv.data)
        assert response_args["status"] == "success"

        # Logout
        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_34_activity_flow_videogame(self):

        """
            Display activity flow in videogame mode
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        assert "Se connecter" in str(rv.data)

    def test_35_graphs_videogame_mode(self):

        """
            Test all graph endpoints in videogame mode
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        assert "Se connecter" in str(rv.data)

    def test_36_push_notifications(self):

        """
            Test push notification subscribe and unsubscribe
        """

        # Login
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        assert "Se connecter" in str(rv.data)

        # Verify subscription has been removed from database
        with self.app.app_context():
            sub = PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/test-endpoint-123").first()
            assert sub is None

        # --- Idempotent re-subscribe: the client resends its subscription on
        #     every login, so re-posting the same endpoint must succeed and keep
        #     a single row (no duplicate / no IntegrityError) ---
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

        rv=self.client.post('/notifications/subscribe', data=json.dumps(subscription_data), content_type='application/json')
        assert json.loads(rv.data)["status"] == "success"

        # Same subscription resent -> still success, still exactly one row
        rv=self.client.post('/notifications/subscribe', data=json.dumps(subscription_data), content_type='application/json')
        assert json.loads(rv.data)["status"] == "success"
        with self.app.app_context():
            assert PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/test-endpoint-123").count() == 1

        # A new endpoint for the same session replaces the old one (unique session_id)
        subscription_data_new = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test-endpoint-456",
            "keys": {
                "p256dh": "another-public-key",
                "auth": "another-auth-token"
            }
        }
        rv=self.client.post('/notifications/subscribe', data=json.dumps(subscription_data_new), content_type='application/json')
        assert json.loads(rv.data)["status"] == "success"
        with self.app.app_context():
            assert PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/test-endpoint-123").first() is None
            assert PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/test-endpoint-456").first() is not None

        # --- Error case: DB error during subscribe returns failure (rollback path) ---
        with patch('cineapp.push.db.session.commit', side_effect=Exception("DB store error")):
            rv=self.client.post('/notifications/subscribe', data=json.dumps(subscription_data_new), content_type='application/json')
            assert json.loads(rv.data)["status"] == "failure"

        # --- Error case: DB error during unsubscribe (L65-67) ---
        with patch('cineapp.push.db.session.commit', side_effect=Exception("DB delete error")):
            rv=self.client.get('/logout', follow_redirects=True)
            assert "Se connecter" in str(rv.data)

        # Subscription should still be in DB since delete failed
        with self.app.app_context():
            sub = PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/test-endpoint-456").first()
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

        # --- notification_send: a 410 Gone endpoint is purged from the DB ---
        with self.app.app_context():
            dead_sub = PushNotification(endpoint_id="https://fcm.googleapis.com/fcm/send/dead-endpoint-410", public_key="dead-pub", auth_token="dead-auth", session_id="dead-session-410", user_id=1)
            db.session.add(dead_sub)
            db.session.commit()

        dead_serialized = [{"endpoint": "https://fcm.googleapis.com/fcm/send/dead-endpoint-410", "keys": {"p256dh": "dead-pub", "auth": "dead-auth"}}]
        gone_response = type('FakeResponse', (), {'status_code': 410})()
        with self.app.app_context():
            with patch('cineapp.push.webpush', side_effect=WebPushException("Gone", response=gone_response)):
                notification_send(dead_serialized, "/chat", "ptitoliv: Hello !")
            assert PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/dead-endpoint-410").first() is None

        # --- notification_send: a 403 (VAPID credentials mismatch) is purged ---
        with self.app.app_context():
            stale_sub = PushNotification(endpoint_id="https://fcm.googleapis.com/fcm/send/stale-endpoint-403", public_key="stale-pub", auth_token="stale-auth", session_id="stale-session-403", user_id=1)
            db.session.add(stale_sub)
            db.session.commit()

        stale_serialized = [{"endpoint": "https://fcm.googleapis.com/fcm/send/stale-endpoint-403", "keys": {"p256dh": "stale-pub", "auth": "stale-auth"}}]
        forbidden_response = type('FakeResponse', (), {'status_code': 403})()
        with self.app.app_context():
            with patch('cineapp.push.webpush', side_effect=WebPushException("Forbidden", response=forbidden_response)):
                notification_send(stale_serialized, "/chat", "ptitoliv: Hello !")
            assert PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/stale-endpoint-403").first() is None

        # --- notification_send: a transient 500 keeps the subscription (no over-purge) ---
        with self.app.app_context():
            live_sub = PushNotification(endpoint_id="https://fcm.googleapis.com/fcm/send/live-endpoint-500", public_key="live-pub", auth_token="live-auth", session_id="live-session-500", user_id=1)
            db.session.add(live_sub)
            db.session.commit()

        live_serialized = [{"endpoint": "https://fcm.googleapis.com/fcm/send/live-endpoint-500", "keys": {"p256dh": "live-pub", "auth": "live-auth"}}]
        error_response = type('FakeResponse', (), {'status_code': 500})()
        with self.app.app_context():
            with patch('cineapp.push.webpush', side_effect=WebPushException("Server error", response=error_response)):
                notification_send(live_serialized, "/chat", "ptitoliv: Hello !")
            survivor = PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/live-endpoint-500").first()
            assert survivor is not None
            db.session.delete(survivor)
            db.session.commit()

        # --- notification_send: a failing purge delete is caught + rolled back (push.py:68-70) ---
        with self.app.app_context():
            rollback_sub = PushNotification(endpoint_id="https://fcm.googleapis.com/fcm/send/rollback-endpoint-410", public_key="rb-pub", auth_token="rb-auth", session_id="rollback-session-410", user_id=1)
            db.session.add(rollback_sub)
            db.session.commit()

        rollback_serialized = [{"endpoint": "https://fcm.googleapis.com/fcm/send/rollback-endpoint-410", "keys": {"p256dh": "rb-pub", "auth": "rb-auth"}}]
        with self.app.app_context():
            with patch('cineapp.push.webpush', side_effect=WebPushException("Gone", response=gone_response)), \
                 patch('cineapp.push.db.session.commit', side_effect=Exception("purge commit failed")):
                notification_send(rollback_serialized, "/chat", "ptitoliv: Hello !")
            # The delete was rolled back on the commit failure, so the row stays.
            survivor = PushNotification.query.filter_by(endpoint_id="https://fcm.googleapis.com/fcm/send/rollback-endpoint-410").first()
            assert survivor is not None
            db.session.delete(survivor)
            db.session.commit()

    def test_37_chat(self):

        """
            Test chat features: page access, SocketIO connection, message sending
        """

        # --- Access chat page (L79) ---
        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

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
        assert "Se connecter" in str(rv.data)

    def test_38_fts_boolean_and_search(self):

        """
            Validate that the in-app FTS search runs in boolean AND mode:
            adding Retour vers le futur 1/2/3 through the regular add wizard
            and searching for the full title must return exactly those 3
            movies, not every show whose name contains any of the tokens
            (which is what NATURAL LANGUAGE mode would return).
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

        # Add each movie via the standard select+confirm flow, hardcoded TMDB ids:
        # 105 = Retour vers le futur (1985)
        # 165 = Retour vers le futur II (1989)
        # 196 = Retour vers le futur III (1990)
        for show_id in ("105", "165", "196"):
            rv=self.client.post('/movie/add/confirm',data=dict(show_id=show_id,origin="F",type="C",submit_confirm=True),follow_redirects=True)
            assert rv.status_code == 200

        # Let's generate the query filter based on the movie name
        rv=self.client.post('/filter',data=dict(search="Retour vers le futur",submit_search=True),follow_redirects=True)
        assert rv.status_code == 200

        # Get the filled datatable based on the filter generated by the query
        args = {'search': {'regex': False, 'value': ''}, 'draw': 1, 'start': 0, 'length': 100, 'order': [{'column': 0, 'dir': 'asc'}], 'columns': [{'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'name', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'director', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'average', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_fav', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_mark', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_when', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.3', 'name': '', 'searchable': True}]}
        rv=self.client.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) == 3, \
            "FTS AND mode regression: expected exactly 3 results for 'Retour vers le futur', got %d (%r)" \
            % (len(response_args), [r["name"] for r in response_args])
        for row in response_args:
            assert "Retour vers le futur" in row["name"], \
                "Unexpected match in FTS results: %r" % row["name"]

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)

    def test_39_igdb_token_refresh_on_401(self):

        """
            A cached IGDB OAuth token may be invalidated by Twitch before its
            local expiry (secret rotation, an old app-token revoked, ...). In
            that case api_request raises HTTPError 401. _igdb_request must purge
            the cached wrapper, get a fresh token and replay the SAME request
            (up to 5 attempts) instead of returning None until the next restart.

            We exercise the real add flow: only the FIRST IGDB call is forced to
            401 (a revoked token can't be produced from the real API); every
            following call — including the token renewal and the replay — hits
            IGDB for real, so a real game (Half-Life, absent from the test DB)
            must still be searched and added despite the injected 401.
        """

        rv=self.client.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert '<span id="topbar-username">ptitoliv</span>' in str(rv.data)

        # Switch to videogame mode
        rv=self.client.get('/switch/videogame', follow_redirects=True)

        # Make the very first IGDB call 401 as if Twitch had silently revoked the
        # cached token. The retry logic purges the cache itself, so no manual reset.
        resp_401 = requests.Response()
        resp_401.status_code = 401
        err_401 = requests.HTTPError("401 Unauthorized")
        err_401.response = resp_401

        real_api_request = IGDBWrapper.api_request
        call_count = 0
        def _api_401_then_real(self_wrapper, endpoint, body):
            nonlocal call_count
            call_count += 1
            # Fail only the first IGDB call with a 401; delegate the rest to the
            # real API so the token renewal and the replay hit IGDB for real.
            if call_count == 1:
                raise err_401
            return real_api_request(self_wrapper, endpoint, body)

        with patch.object(IGDBWrapper, 'api_request', autospec=True, side_effect=_api_401_then_real):
            # Real IGDB search: the first call 401s, _igdb_request renews the token
            # and replays, so the real game is still returned by the search.
            rv=self.client.post('/videogame/add/select',data=dict(search="Half-Life",submit_search=True))
            parsed_html=BeautifulSoup(rv.data,"html.parser")
            list_shows=parsed_html.find_all('label', class_='wizard-result')
            igdb_id_hl=None
            for cur_show in list_shows:
                if "Half-Life" in cur_show.text:
                    radio = cur_show.find('input', {'type': 'radio'})
                    if radio:
                        igdb_id_hl = radio['value']
                    break
            assert igdb_id_hl is not None

            rv=self.client.post('/videogame/add/confirm',data=dict(show_id=igdb_id_hl,origin="F",type="ACT",submit_confirm=True),follow_redirects=True)
            assert "Jeu vidéo ajouté" in rv.data.decode("utf-8")

        # The first IGDB call really returned 401 and the retry recovered it
        # (otherwise the search would have returned no result and no game added).
        assert call_count >= 2

        with self.app.app_context():
            half_life = VideoGame.query.filter_by(external_id=int(igdb_id_hl), external_source="igdb").first()
            assert half_life is not None
            # Remove the game so later tests are unaffected.
            db.session.delete(half_life)
            db.session.commit()

        rv=self.client.get('/logout', follow_redirects=True)
        assert "Se connecter" in str(rv.data)
