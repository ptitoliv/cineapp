# -*- coding: utf-8 -*-

from future import standard_library
standard_library.install_aliases()
import os, sys, json
from cineapp import app, db
from cineapp.models import User, Type, Origin
from bcrypt import hashpw, gensalt
import unittest
import tempfile
import shutil
import io

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
        
        db.create_all()
        
        # Create the default user for tests
        hashed_password=hashpw("toto1234".encode('utf-8'),gensalt())
        u = User()
        u.nickname="ptitoliv"
        u.password=hashed_password
        u.email="ptitoliv@ptitoliv.net"
        u.notifications={
            "notif_own_activity" : True,
            "notif_movie_add" : True,
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
        rv=self.app.get('/movies/add')
        assert "Ajout d&#39;un film" in str(rv.data)
        
        # Fill the movie title
        rv=self.app.post('/movies/add/select',data=dict(search="tuche",submit_search=True))
        assert "Les Tuche" in str(rv.data)
        
        # Select the movie
        rv=self.app.post('/movies/add/confirm',data=dict(movie="66129",submit_select=True))
        assert "Ajouter le film" in str(rv.data)
        
        # Store the movie into database
        rv=self.app.post('/movies/add/confirm',data=dict(movie_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
        assert "Film ajout" in str(rv.data)
        assert "Affiche" in str(rv.data)
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_05_upload_avatar(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        with open(self.dir + '/ressources/test_avatar.png', 'rb') as img1:
                img1BytesIO = io.BytesIO(img1.read())
        
        rv=self.app.post('/my/profile',
                             content_type='multipart/form-data',
                             data=dict(email="ptitoliv+test@ptitoliv.net",upload_avatar=(img1BytesIO, 'test_avatar.png')), follow_redirects=True)
        assert 'Informations mises à jour' in rv.data.decode("utf-8")
        assert "Avatar correctement mis à jour" in rv.data.decode("utf-8")
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_06_mark_movie(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.app.post('/movies/mark/1',data=dict(mark=10,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note ajout" in str(rv.data)
        
        # We are logged => mark the movie
        rv=self.app.post('/movies/mark/1',data=dict(mark=16,comment="cool",seen_where="C",submit_mark=1,submit_mark_slack=1),follow_redirects=True)
        assert "Note mise" in str(rv.data)
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_07_comment_mark(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.app.post('/json/add_mark_comment',data=dict(movie_id=1,dest_user=1,comment="plop"),follow_redirects=True)
        rv=self.app.get('/movies/show/1', follow_redirects=True)
        assert "plop" in str(rv.data) 
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_08_random_movie(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.app.get('/movies/show/random', follow_redirects=True)
        assert "Sortie" in str(rv.data) 
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_09_search_movie(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.app.get('/movies/list', follow_redirects=True)
        assert "Liste des films" in str(rv.data)
        
        args = {'search': {'regex': False, 'value': ''}, 'draw': 1, 'start': 0, 'length': 100, 'order': [{'column': 0, 'dir': 'asc'}], 'columns': [{'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'name', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'director', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'average', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_fav', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_mark', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'my_when', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.1', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.2', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_favs.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_marks.3', 'name': '', 'searchable': True}, {'orderable': True, 'search': {'regex': False, 'value': ''}, 'data': 'other_when.3', 'name': '', 'searchable': True}]}
        
        rv=self.app.get('/movies/json', data=dict(args=json.dumps(args)),headers=[('X-Requested-With', 'XMLHttpRequest')], follow_redirects=True)

        response_args=json.loads(rv.data)["data"]
        assert "Les Tuche" in response_args[0]["name"]
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

    def test_10_edit_mark_movie(self):

        rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
        assert "Welcome <strong>ptitoliv</strong>" in str(rv.data) 
        
        # We are logged => mark the movie
        rv=self.app.post('/json/edit_mark_comment',data=dict(comment_id=1,comment_text="plup"),follow_redirects=True)
        rv=self.app.get('/movies/show/1', follow_redirects=True)
        assert "plup" in str(rv.data) 
        
        # Delete the comment    
        rv=self.app.post('/json/delete_mark_comment',data=dict(comment_id=1),follow_redirects=True)
        rv=self.app.get('/movies/show/1', follow_redirects=True)
        assert "plup" not in str(rv.data) 
        
        rv=self.app.get('/logout', follow_redirects=True)
        assert "Welcome to CineApp" in str(rv.data)

if __name__ == '__main__':
    unittest.main()

