# -*- coding: utf-8 -*-

from future import standard_library
standard_library.install_aliases()
import os, sys, json
from cineapp import app, db
from cineapp import slack
from cineapp.models import User, Type, Origin
from bcrypt import hashpw, gensalt
import unittest
import tempfile
import shutil
import io
from bs4 import BeautifulSoup
from flask_migrate import upgrade

class FlaskrTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Define the test directory
        cls.dir = os.path.dirname(__file__)
        
        cls.app = app.test_client()
        
        if os.environ.get('LOCAL') == "yes":
                app.config.from_pyfile('../configs/settings_tests_local.cfg')
        else:
                app.config.from_pyfile('../configs/settings_test.cfg')
        
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
        
        db.session.add(u)
        db.session.commit()

    @classmethod
    def tearDownClass(cls):
        # Remove directories
        shutil.rmtree(app.config['POSTERS_PATH'])
        shutil.rmtree(app.config['AVATARS_FOLDER'])
        
        db.session.commit()
        db.engine.execute("DROP TABLE alembic_version")
        db.drop_all()

    def test_01_populateUsers(self):
        hashed_password=hashpw("toto1234".encode('utf-8'),gensalt())
        u = User()
        u.nickname="foo"
        u.password=hashed_password
        u.email="foo@bar.net"
        
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
        u=User.query.get(1);

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        with open(self.dir + '/ressources/test_avatar.png', 'rb') as img1:
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
        
        rv=self.app.get('/movie/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)

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

if __name__ == '__main__':
    unittest.main()
