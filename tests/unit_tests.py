# -*- coding: utf-8 -*-

from future import standard_library
standard_library.install_aliases()
import os, sys, json
from cineapp import app, db, mail
from cineapp import slack
from cineapp.models import User, Type, Origin, Mark, Movie
from datetime import datetime
from bcrypt import hashpw, gensalt
import unittest
import tempfile
import shutil
import io
from bs4 import BeautifulSoup
from flask_migrate import upgrade
from sqlalchemy import text

class FlaskrTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):

        # Load the file specified by the APP_CONFIG_FILE environment variable
        # Variables defined here will override those in the default configuration
        app.config.from_envvar('APP_CONFIG_FILE')

        # Init with default connection string
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['TESTING'] = True
        app.config['MAIL_SUPPRESS_SEND'] = True
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        cls.app = app.test_client()
        cls.context = app.app_context()

        with app.app_context():
            db.drop_all()
        
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['TESTING'] = True

        # Delete the directories if they exisits
        if os.path.isdir(os.path.join(app.config['POSTERS_PATH'])):
                shutil.rmtree(app.config['POSTERS_PATH'])
        
        if os.path.isdir(os.path.join(app.config['AVATARS_FOLDER'])):
                shutil.rmtree(app.config['AVATARS_FOLDER'])
        
        # Create directories
        os.makedirs(app.config['POSTERS_PATH'])
        os.makedirs(app.config['AVATARS_FOLDER'])

        # Create the database
        with app.app_context():
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
        
        with app.app_context():
            db.session.add(u)
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        # Remove directories
        shutil.rmtree(app.config['POSTERS_PATH'])
        shutil.rmtree(app.config['AVATARS_FOLDER'])
        
        with app.app_context():
            db.session.commit()
            db.session.execute(text("DROP TABLE alembic_version"))
            db.drop_all()

    def test_01_populateUsers(self):
        with app.app_context():
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

    def test_02_index(self):
        rv = self.app.get('/login')
        assert "Welcome to CineApp" in str(str(rv.data))

    def test_03_login_logout(self):

        # Bad user
        rv=self.app.post('/login',data=dict(username="user",password="pouet"), follow_redirects=True)
        assert "Mauvais utilisateur !" in str(str(rv.data))
        
        # Bad password
        rv=self.app.post('/login',data=dict(username="ptitoliv",password="pouet"), follow_redirects=True)
        assert "Mot de passe incorrect !" in str(str(rv.data))
        
        # Good login
        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(str(rv.data))
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(str(rv.data))
        
        # Login as guest
        rv=self.app.post('/login',data=dict(username="guest",password="guest"), follow_redirects=True)
        assert "Welcome <strong>Guest</strong>" in str(str(rv.data))
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(str(rv.data))

    def test_04_add_movie(self):
        with app.app_context():
            # Add types
            t = Type()
            t.id="C"
            t.type="Comédie"
            
            db.session.add(t)
            db.session.commit()
            
            # Add origin
            o = Origin()
            o.id="F"
            o.origin="Francais"
            
            db.session.add(o)
            db.session.commit()

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # We are logged => add the movie
        rv=self.app.get('/movie/add')
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajout d'un film" == parsed_html.find(id="add_wizard_label").text
        
        # Fill the movie title
        rv=self.app.post('/movie/add/select',data=dict(search="Les Tuche",submit_search=True))
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
        rv=self.app.post('/movie/add/confirm',data=dict(show="66129",submit_select=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajouter le film" == parsed_html.find(id="submit_confirm")['value']
        
        # Store the movie into database
        rv=self.app.post('/movie/add/confirm',data=dict(show_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
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
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_05_edit_profile(self):

        # Fetch the user in order to fill the form with the current notifications parameters
        # Otherwise, when we post that form, all notifications are set to false
        with app.app_context():
            u=User.query.get(1);
        
        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        avatar_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
            "ressources/test_avatar.png")
        
        with open(avatar_path, 'rb') as img1:
                img1BytesIO = io.BytesIO(img1.read())
        
        rv=self.app.post('/my/profile',
                             content_type='multipart/form-data',
                             data=dict(email="ptitoliv+test@ptitoliv.net",upload_avatar=(img1BytesIO, 'test_avatar.png'),
                             notif_own_activity=u.notifications["notif_own_activity"],
                             notif_show_add=u.notifications["notif_show_add"],
                             notif_homework_add=u.notifications["notif_homework_add"],
                             notif_mark_add=u.notifications["notif_mark_add"],
                             notif_comment_add=u.notifications["notif_comment_add"],
                             notif_favorite_update=u.notifications["notif_favorite_update"],
                             notif_chat_message=u.notifications["notif_chat_message"],
                             notif_slack=u.notifications["notif_slack"]), follow_redirects=True)
        
        assert 'Informations mises à jour' in rv.data.decode("utf-8")
        assert "Avatar correctement mis à jour" in rv.data.decode("utf-8")
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_06_mark_movie(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.app.post('/movie/mark/1',data=dict(mark=10,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note ajout" in str(rv.data)
        
        # We are logged => mark the movie
        rv=self.app.post('/movie/mark/1',data=dict(mark=16,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note mise" in str(rv.data)
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_07_comment_mark(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.app.post('/json/add_mark_comment',data=dict(show_id=1,dest_user=1,comment="plop"),follow_redirects=True)
        rv=self.app.get('/movie/display/1', follow_redirects=True)
        assert "plop" in str(rv.data) 
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_08_random_movie(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.app.get('/movie/display/random', follow_redirects=True)
        assert "Fiche" in str(rv.data) 
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_09_search_movie(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.app.get('/movie/list', follow_redirects=True)
        assert "Liste des films" in str(rv.data)
        
        args = {'search': {'regex': False, 'value': ''}, 'draw': 1, 'start': 0, 'length': 100, 'order': [{'column': 0, 'dir': 'asc'}], 'columns': [{'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'name', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'director', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'average', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_fav', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_mark', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_when', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.3', 'name': '', 'searchable': True}]}
        
        rv=self.app.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)

        response_args=json.loads(rv.data)["data"]
        assert "Les Tuche" in response_args[0]["name"]
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_10_edit_mark_movie(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.app.post('/json/edit_mark_comment',data=dict(comment_id=1,comment_text="plup"),follow_redirects=True)
        rv=self.app.get('/movie/display/1', follow_redirects=True)
        assert "plup" in str(rv.data) 
        
        # Delete the comment    
        rv=self.app.post('/json/delete_mark_comment',data=dict(comment_id=1),follow_redirects=True)
        rv=self.app.get('/movie/display/1', follow_redirects=True)
        assert "plup" not in str(rv.data) 
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_11_slack_fail_cases(self):

        # Let's try to send a slack notification which is going to fail because we don't have Slack Token

        # First : a notification without configured token
        temp_slack_token=app.config["SLACK_TOKEN"]
        app.config["SLACK_TOKEN"]=None
        assert slack.slack_mark_notification(None,app,"movie") == -1
        app.config["SLACK_TOKEN"]=temp_slack_token

        # Then, A notification with a bad channel configured
        slack_channel = slack.SlackChannel(app.config["SLACK_TOKEN"],"achannelthatdoesentexist")

        # Syntex tip : https://ongspxm.gitlab.io/blog/2016/11/assertraises-testing-for-errors-in-unittest/
        with self.assertRaises(SystemError):slack_channel.send_message("ZBRAH")

        # Let's do the same but with the slack_mark_notification method (In order to catch the exception)
        assert slack.slack_mark_notification(None,app,"movie") == 1

    def test_12_add_tvshow(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => add the movie
        rv=self.app.get('/tvshow/add')
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajout d'une série" == parsed_html.find(id="add_wizard_label").text
        
        # Fill the show title
        rv=self.app.post('/tvshow/add/select',data=dict(search="Babylon 5",submit_search=True))
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
        rv=self.app.post('/tvshow/add/confirm',data=dict(show="3137",submit_select=True))
        parsed_html=BeautifulSoup(rv.data,"html.parser")
        assert u"Ajouter la série" == parsed_html.find(id="submit_confirm")['value']
        
        # Store the movie into database
        rv=self.app.post('/tvshow/add/confirm',data=dict(show_id="3137",origin="F",type="C",submit_confirm=True),follow_redirects=True)
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
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_13_mark_tvshow(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the show
        rv=self.app.post('/tvshow/mark/2',data=dict(mark=10,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note ajout" in str(rv.data)
        
        # We are logged => mark the show
        rv=self.app.post('/tvshow/mark/2',data=dict(mark=16,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note mise" in str(rv.data)
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_14_comment_mark(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => comment the mark
        rv=self.app.post('/json/add_mark_comment',data=dict(show_id=2,dest_user=1,comment="plop"),follow_redirects=True)
        rv=self.app.get('/tvshow/display/2', follow_redirects=True)
        assert "plop" in str(rv.data) 
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_15_random_show(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        rv=self.app.get('/tvshow/display/random', follow_redirects=True)
        assert "Fiche" in str(rv.data) 
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_16_switch(self):

        """
            This test tries to switch between different mode
        """

        modes={ 'movie': 'films', 'tvshow': 'séries' };

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # Switch between availables modes
        for key, value in modes.items():
    
            # Let's change mode
            rv=self.app.get('/switch/%s' % key, follow_redirects=True)
            assert ("Liste des %s" % value) in rv.data.decode('utf-8')

        # Test an unkown category
        rv=self.app.get('/switch/unkown')
        assert rv.status_code == 404

        # Test a direct acccess to an unkown category
        rv=self.app.get('/unkown/list')
        assert rv.status_code == 404

        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_17_add_user(self):

        """
            User add test
        """

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # First test ==> Add successfully a user
        rv=self.app.post('/users/add', data=dict(username="toto",email="toto@toto.com",password="toto",confirm="toto"))
        assert "Utilisateur ajouté" in rv.data.decode('utf-8')

        # Second test ==> Try to add the same user
        rv=self.app.post('/users/add', data=dict(username="toto",email="toto@toto.com",password="toto",confirm="toto"))
        assert "déjà existant" in rv.data.decode("utf-8")

        # Third test ==> Test form validation (Empty form)
        rv=self.app.post('/users/add', data=dict())
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        for cur_field in [ "div_username", "div_email", "div_password", "div_confirm" ]:
            assert u"Ce champ est requis" in parsed_html.find(id=cur_field).text

        # Fourth test ==> Field validation
        rv=self.app.post('/users/add', data=dict(username="tutu",email="tutu",password="1224",confirm="tata"))
        parsed_html=BeautifulSoup(rv.data,"html.parser")

        test_fields={ 'div_email': 'Adresse E-Mail Incorrecte', 
            'div_password': 'Les mots de passe ne correspondent pas',
            'div_confirm': 'Les mots de passe ne correspondent pas' 
            }

        for key, value in test_fields.items():
            assert value in parsed_html.find(id=key).text

        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_18_guest_mode(self):

        """
            Test app in guest mode
        """
        # Login
        rv=self.app.post('/login',data=dict(username="guest",password="guest"), follow_redirects=True)
        assert "Welcome <strong>Guest</strong>" in str(rv.data) 

        rv=self.app.post('/filter',data=dict(search="Les Tuche",submit_search=True),follow_redirects=True)  
        assert "Recherche Personnalisée: Les Tuche" in rv.data.decode('utf-8')

        args = {'search': {'regex': False, 'value': ''}, 'draw': 1, 'start': 0, 'length': 100, 'order': [{'column': 0, 'dir': 'asc'}], 'columns': [{'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'name', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'director', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'average', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_fav', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_mark', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_when', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.3', 'name': '', 'searchable': True}]}
        
        rv=self.app.post('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert "Les Tuche" in response_args[0]["name"]

        # Logout
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_19_activity_flow(self):

        """
            Display activity flow and data 
        """

        # Login
        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # Check if the activity flow route is working
        modes={ 'tvshow': 'séries', 'movie': 'films' };

        # Switch between availables modes
        for key, value in modes.items():

            # Let's change mode
            rv=self.app.get('/switch/%s' % key, follow_redirects=True)
            rv=self.app.get('/activity/show', follow_redirects=True)
            assert "Flux d&#39;activité des %s" % value in str(rv.data.decode('utf-8'))
        
        # Now test the datatable part
        args={'draw': 1, 'columns': [{'data': 'entry_type', 'name': '', 'searchable': True, 'orderable': False, 'search': {'value': '', 'regex': False, 'fixed': []}}, {'data': None, 'name': '', 'searchable': True, 'orderable': False, 'search': {'value': '', 'regex': False, 'fixed': []}}, {'data': 'entry_text', 'name': '', 'searchable': True, 'orderable': False, 'search': {'value': '', 'regex': False, 'fixed': []}}], 'order': [], 'start': 0, 'length': 100, 'search': {'value': '', 'regex': False, 'fixed': []}}

        rv=self.app.post('/activity/update', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)
        response_args=json.loads(rv.data)["data"]
        assert len(response_args) > 0

        # Logout
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_20_homework(self):

        """
            Display activity flow and data 
        """

        with app.app_context():

            # Add additionl data in order to test that we can't remove an homework 
            # given by another user
            movie=Movie(name="Movie",original_name="Original Movie", release_date="2000-01-01", origin="F", director="A guy", duration=142)
            mark=Mark(user_id=1,show_id=3,homework_who=2,homework_when=datetime.now())
            db.session.add(movie)
            db.session.add(mark)
            db.session.commit()

            # Add a movie already with a mark
            mark=Mark(user_id=2,show_id=3,homework_who=1,homework_when=datetime.now(),mark=14,seen_where="C",seen_when=datetime.now())
            db.session.add(movie)
            db.session.add(mark)
            db.session.commit()

        # Login
        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 

        # Give an homework from user 1 to user 2
        with mail.record_messages() as outbox:
            rv=self.app.get('/homework/add/1/2',follow_redirects=True)
            assert "Devoir ajouté" in rv.data.decode('utf-8')
            assert "Attribution d'un devoir" in outbox[0].subject

        # Give an homework from user 1 to user 2 for a show already with a mark
        with mail.record_messages() as outbox:
            rv=self.app.get('/homework/add/3/2',follow_redirects=True)
            assert "Impossible de créer le devoir. Une note existe déjà" in rv.data.decode('utf-8')

        # List homeworks
        rv=self.app.get('/homework/list', follow_redirects=True)
        assert "Liste des devoirs" in rv.data.decode('utf-8')
        assert "A guy" in rv.data.decode('utf-8')

        # List filtered homeworks
        rv=self.app.post('/homework/list', data=dict(from_user_filter=1,to_user_filter=2),follow_redirects=True)
        assert "Liste des devoirs" in rv.data.decode('utf-8')
        assert "Les Tuche" in rv.data.decode('utf-8')

        # Give an incorrect homework
        rv=self.app.get('/homework/add/3/10',follow_redirects=True)
        assert "Impossible de créer le devoir" in rv.data.decode('utf-8')

        # Delete an homework
        with mail.record_messages() as outbox:
            rv=self.app.get('/homework/delete/1/2',follow_redirects=True)
            assert "Devoir annulé" in rv.data.decode('utf-8')
            assert "Annulation d'un devoir" in outbox[0].subject

        # Delete an incorrect homework
        rv=self.app.get('/homework/delete/3/10',follow_redirects=True)
        assert "Ce devoir n&#39;existe pas" in rv.data.decode('utf-8')

        # Delete an unauthorized homework
        rv=self.app.get('/homework/delete/3/1',follow_redirects=True)
        assert "Vous n&#39;avez pas le droit de supprimer ce devoir" in rv.data.decode('utf-8')

        # Delete an homework already with a mark
        with mail.record_messages() as outbox:
            rv=self.app.get('/homework/delete/3/2',follow_redirects=True)
            assert "Impossible de supprimer le devoir - Une note existe déjà" in rv.data.decode('utf-8')

        # Logout
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)
