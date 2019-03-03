# -*- coding: utf-8 -*-

import os, sys
from cineapp import app, db
from cineapp.models import User, Type, Origin
from bcrypt import hashpw, gensalt
import unittest
import tempfile
import shutil
import StringIO

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
	assert "Welcome to CineApp" in rv.data

    def test_03_login_logout(self):

	# Bad user
	rv=self.app.post('/login',data=dict(username="user",password="pouet"), follow_redirects=True)
	assert "Mauvais utilisateur !" in rv.data 

	# Bad password
	rv=self.app.post('/login',data=dict(username="ptitoliv",password="pouet"), follow_redirects=True)
	assert "Mot de passe incorrect !" in rv.data 

	# Good login
	rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
	assert "Welcome <strong>ptitoliv</strong>" in rv.data 

	rv=self.app.get('/logout', follow_redirects=True)
	assert "Welcome to CineApp" in rv.data

	# Login as guest
	rv=self.app.post('/login',data=dict(username="guest",password="guest"), follow_redirects=True)
	assert "Welcome <strong>Guest</strong>" in rv.data 

	rv=self.app.get('/logout', follow_redirects=True)
	assert "Welcome to CineApp" in rv.data

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
	assert "Welcome <strong>ptitoliv</strong>" in rv.data 

	# We are logged => add the movie
	rv=self.app.get('/movies/add')
	assert "Ajout d&#39;un film" in rv.data

	# Fill the movie title
	rv=self.app.post('/movies/add/select',data=dict(search="tuche",submit_search=True))
	assert "Les Tuche" in rv.data

	# Select the movie
	rv=self.app.post('/movies/add/confirm',data=dict(movie="66129",submit_select=True))
	assert "Ajouter le film" in rv.data

	# Store the movie into database
	rv=self.app.post('/movies/add/confirm',data=dict(movie_id="66129",origin="F",type="C",submit_confirm=True),follow_redirects=True)
	assert "Film ajout" in rv.data
	assert "Affiche" in rv.data

	rv=self.app.get('/logout', follow_redirects=True)
	assert "Welcome to CineApp" in rv.data

    def test_05_upload_avatar(self):

	rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
	assert "Welcome <strong>ptitoliv</strong>" in rv.data 

	print self.dir	
	with open(self.dir + '/ressources/test_avatar.png', 'rb') as img1:
        	img1StringIO = StringIO.StringIO(img1.read())

	rv=self.app.post('/my/profile',
                             content_type='multipart/form-data',
			     data=dict(email="ptitoliv+test@ptitoliv.net",upload_avatar=(img1StringIO, 'test_avatar.png')), follow_redirects=True)

	assert "Informations mises à jour" in rv.data
	assert "Avatar correctement mis à jour" in rv.data

	rv=self.app.get('/logout', follow_redirects=True)
	assert "Welcome to CineApp" in rv.data

    def test_06_mark_movie(self):

	rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
	assert "Welcome <strong>ptitoliv</strong>" in rv.data 

	# We are logged => mark the movie
	rv=self.app.post('/movies/mark/1',data=dict(mark=10,comment="cool",seen_where="C",submit_mark=1),follow_redirects=True)
	assert "Note ajout" in rv.data

	rv=self.app.get('/logout', follow_redirects=True)
	assert "Welcome to CineApp" in rv.data

    def test_07_comment_mark(self):

	rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
	assert "Welcome <strong>ptitoliv</strong>" in rv.data 

	# We are logged => mark the movie
	rv=self.app.post('/json/add_mark_comment',data=dict(movie_id=1,dest_user=1,comment="plop"),follow_redirects=True)
	rv=self.app.get('/movies/show/1', follow_redirects=True)
	assert "plop" in rv.data 

	rv=self.app.get('/logout', follow_redirects=True)
	assert "Welcome to CineApp" in rv.data

    def test_08_random_movie(self):

	rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
	assert "Welcome <strong>ptitoliv</strong>" in rv.data 

	# We are logged => mark the movie
	rv=self.app.get('/movies/show/random', follow_redirects=True)
	assert "Sortie" in rv.data 

	rv=self.app.get('/logout', follow_redirects=True)
	assert "Welcome to CineApp" in rv.data

    def test_09_search_movie(self):

	rv=self.app.post('/login',data=dict(username="ptitoliv",password="toto1234"), follow_redirects=True)
	assert "Welcome <strong>ptitoliv</strong>" in rv.data 

	# We are logged => mark the movie
	rv=self.app.get('/movies/list', follow_redirects=True)
	assert "Liste des films" in rv.data

	rv=self.app.get('/logout', follow_redirects=True)
	assert "Welcome to CineApp" in rv.data

if __name__ == '__main__':
    unittest.main()
