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
			continue
		break

	return json.load(data)

def download_poster(movie):

	""" Function that downloads the poster from the tvmdb and update the database with the correct path
	"""
	try:
		img = urllib2.urlopen(movie.poster_path)
		localFile = open(os.path.join(app.config['POSTERS_PATH'], os.path.basename(movie.poster_path)), 'wb')
		localFile.write(img.read())
		localFile.close()

	except Exception as e:
		print e
		return False

	# Let's update the field in the database
	movie.poster_path=os.path.basename(movie.poster_path)
	try:
		db.session.commit()
	except:
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
			complete_list.append(get_movie(cur_movie['id'],False))

	return complete_list

def get_movie(id,fetch_poster=True):
	"""
		Function that fill a movie object using TVMDB database
	"""

	# Fetch the movie data
	movie=tmvdb_connect(os.path.join(app.config['API_URL'],("movie/" + str(id) + "?api_key=" + app.config['API_KEY'] + "&append_to_response=credits,details&language=fr")))

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

	# Fetch the poster if we have to
	if fetch_poster == True:

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

	# Create the movie object
	movie_obj=Movie(name=movie['title'],
		release_date=movie['release_date'],
		url="http://www.themoviedb.org/movie/" + str(id),
		tmvdb_id=id,
		poster_path=url,
		director=director
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
