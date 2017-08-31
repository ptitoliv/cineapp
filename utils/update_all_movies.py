# -*- coding: utf-8 -*-
#!flask/bin/python

"""
	Script that update all movies stored in the database with a tmvdb_id
"""

import json, urllib2,sys, time, urllib, os
from cineapp import app,db, tvmdb
from cineapp.models import Movie

# Fetch objects only where we have a tmdb_id
movies=Movie.query.filter(Movie.original_name==None)

# Process each movie
for movie in movies:

	temp_movie=tvmdb.get_movie(movie.tmvdb_id,True)

	if temp_movie == None:
		print u"%s non référencé" % movie.name
		continue

	# Update the movie
	movie.name=temp_movie.name
	movie.original_name=temp_movie.original_name
	movie.release_date=temp_movie.release_date
	movie.url=temp_movie.url
	movie.tmvdb_id=temp_movie.tmvdb_id
	movie.director=temp_movie.director
	movie.overview=temp_movie.overview
	movie.duration=temp_movie.duration

	try:
		db.session.add(movie)
		db.session.flush()
		db.session.commit()
		print u"%s mis à jour avec succès" % movie.name
	except:
		print u"Impossible de mettre à jour %s" % movie.name
