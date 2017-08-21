# -*- coding: utf-8 -*-
import json, urllib2,sys, time, urllib, os, math
from datetime import datetime
from cineapp import app,db
from cineapp.models import Movie

def tmvdb_connect(url):
	"""
		Internal function which handles connection to the API
		using the API rate limiting of the API
	"""
	while True:
		try:
			data=urllib2.urlopen(url)
			remain=int(data.info().getheader('X-RateLimit-Remaining'))
			if remain < 2:
				timestamp_now=time.time()
				timestamp_reset=int(data.info().getheader('X-RateLimit-Reset'))

				if timestamp_now < timestamp_reset:
					delay=math.ceil(timestamp_reset-timestamp_now)
					time.sleep(delay)

		except urllib2.HTTPError:
			return None
		break

	return json.load(data)

def download_poster(url):

	""" Function that downloads the poster from the tvmdb and update the database with the correct path
	"""
	try:
		img = urllib2.urlopen(url)
		localFile = open(os.path.join(app.config['POSTERS_PATH'], os.path.basename(url)), 'wb')
		localFile.write(img.read())
		localFile.close()

	except Exception as e:
		return False

	# If we are here, everything is okay
	return True

def search_movies(query,page=1):

	"""
		Function that query tvmdb.org and return a list of movies
	"""
	# Local variables
	languages_list=["fr"]
	complete_list=[]

	# Query the API using the query in parameter
	for cur_language in languages_list:
		movies_list=tmvdb_connect(os.path.join(app.config['API_URL'],("search/movie?api_key=" + app.config['API_KEY'] + "&language=" + cur_language + "&query=" + urllib.quote(query.encode('utf-8')))) + "&page=" + str(page))

		for cur_movie in movies_list['results']:
			temp_movie=get_movie(cur_movie['id'],False)
			# Only append if we have a real movie object
			if temp_movie != None:
				complete_list.append(temp_movie)

	return complete_list

def get_movie(id,fetch_poster=True):
	"""
		Function that fill a movie object using TVMDB database
	"""

	# Check if there is an id. If not return None
	if id == None:
		return None

	# Fetch the movie data
	movie=tmvdb_connect(os.path.join(app.config['API_URL'],("movie/" + str(id) + "?api_key=" + app.config['API_KEY'] + "&append_to_response=credits,details&language=fr")))

	# Check if we did a successfull search using the API
	if movie == None:
		return None

	# Fetch the director form the casting
	director=""
	for cur_guy in movie['credits']['crew']:
		if cur_guy['job'] == "Director":
			director+=cur_guy["name"] + " / "

	# Remove the last slash if it exists
	director=director.rstrip(' / ')

	if director == "":
		director="Inconnu"

	# Initialize url variable
	url = None

	# Fetch global configuration parameters
	config_api=tmvdb_connect(os.path.join(app.config['API_URL'], "configuration?api_key=" + app.config['API_KEY'] +"&language=fr"))
	base_url=config_api['images']['secure_base_url']

	# Try to get the poster in French
	movie_poster=tmvdb_connect(os.path.join(app.config['API_URL'],("movie/" + str(id) + "/images?api_key=" + app.config['API_KEY'] + "&language=fr&include_image_language=fr,null")))

	# Fetch poster url !
	try:
		url = base_url + 'w185' + movie_poster['posters'][0]['file_path']
	except IndexError:

		# No poster with the french or null language= => Fallback in english
		movie_poster=tmvdb_connect(os.path.join(app.config['API_URL'],("movie/" + str(id) + "/images?api_key=" + app.config['API_KEY'])))

		try:
			url = base_url + 'w185' + movie_poster['posters'][0]['file_path']
		except IndexError:
			pass

	# Download the poster and update the database
	if fetch_poster == True:
		if url and download_poster(url):
			url=os.path.basename(url)
		else:
			url=None

	# Create the movie object
	movie_obj=Movie(name=movie['title'],
		release_date=movie['release_date'],
		original_name=movie['original_title'],
		url=os.path.join(app.config['TMVDB_BASE_URL'],str(id)),
		tmvdb_id=id,
		poster_path=url,
		director=director,
		overview=movie['overview'],
		duration=movie['runtime']
	)

	return movie_obj

def search_page_number(query):
	"""
		Function that returns how many result page we're going to handle for a specific query
	"""

	# Local variables
	languages_list=["fr"]

	# Query the API using the query in parameter
	for cur_language in languages_list:
		result=tmvdb_connect(os.path.join(app.config['API_URL'],("search/movie?api_key=" + app.config['API_KEY'] + "&language=" + cur_language + "&query=" + urllib.quote(query.encode('utf-8')))))

	# Return the page number if we have someone to return
	if result != None:
		return result["total_pages"]
	else:
		return -1

if __name__ == "__main__":
	test=search_movies("tuche")
	for cur_test in test:
		print cur_test

	movie=get_movie(550)
	print movie.name
	print movie.director
	print movie.release_date
	print movie.poster_path
