# -*- coding: utf-8 -*-
from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
from builtins import str
import json, sys, time, urllib.request, urllib.parse, urllib.error, os, math
from urllib.request import urlopen
from datetime import datetime
from cineapp import app,db
from cineapp.models import Movie,TVShow
from flask import g

# Conversion from show_type
tmvdb_mode={ "movies": "movie", "tvshows": "tv" }

def tmvdb_connect(url):
    """
        Internal function which handles connection to the API
        using the API rate limiting of the API
    """
    try:
        data=urlopen(url)
    
    except urllib.error.HTTPError:
        return None

    return json.load(data)

def download_poster(url):

    """ Function that downloads the poster from the tvmdb and update the database with the correct path
    """
    try:
        img = urlopen(url)
        localFile = open(os.path.join(app.config['POSTERS_PATH'], os.path.basename(url)), 'wb')
        localFile.write(img.read())
        localFile.close()

    except Exception as e:
        return False

    # If we are here, everything is okay
    return True

def search_shows(query,page=1):

    """
        Function that query tvmdb.org and return a list of shows
    """
    # Local variables
    languages_list=["fr"]
    complete_list=[]

    # Query the API using the query in parameter
    for cur_language in languages_list:
        shows_list=tmvdb_connect(os.path.join(app.config['API_URL'],("search/" + tmvdb_mode[g.show_type] + "?api_key=" + app.config['API_KEY'] + "&language=" + cur_language + "&query=" + urllib.parse.quote(query.encode('utf-8')))) + "&page=" + str(page))
        app.logger.info("URL de recherche: %s" % os.path.join(app.config['API_URL'],("search/" + tmvdb_mode[g.show_type] + "?api_key=" + app.config['API_KEY'] + "&language=" + cur_language + "&query=" + urllib.parse.quote(query.encode('utf-8')))))

        for cur_show in shows_list['results']:
            temp_show=get_show(cur_show['id'],False)

            # Only append if we have a real show object
            if temp_show != None:
                complete_list.append(temp_show)

    return complete_list

def get_show(id,fetch_poster=True,show_type=None):
    """
        Function that fill a show object using TVMDB database
    """


    # Check if there is an id. If not return None
    if id == None:
        return None

    # Fetch the show data
    show=tmvdb_connect(os.path.join(app.config['API_URL'],(tmvdb_mode[g.show_type] + "/" + str(id) + "?api_key=" + app.config['API_KEY'] + "&append_to_response=credits,details&language=fr")))

    # Check if we did a successfull search using the API
    if show == None:
        return None


    # Initialize url variable
    url = None

    # Fetch global configuration parameters
    config_api=tmvdb_connect(os.path.join(app.config['API_URL'], "configuration?api_key=" + app.config['API_KEY'] +"&language=fr"))
    base_url=config_api['images']['secure_base_url']

    # Try to get the poster in French
    show_poster=tmvdb_connect(os.path.join(app.config['API_URL'],(tmvdb_mode[g.show_type] + "/" + str(id) + "/images?api_key=" + app.config['API_KEY'] + "&language=fr&include_image_language=fr,null")))

    # Fetch poster url !
    try:
        url = base_url + 'w185' + show_poster['posters'][0]['file_path']
    except (IndexError,TypeError):

        # No poster with the french or null language= => Fallback in english
        show_poster=tmvdb_connect(os.path.join(app.config['API_URL'],(tmvdb_mode[g.show_type] + "/" + str(id) + "/images?api_key=" + app.config['API_KEY'])))

        try:
            url = base_url + 'w185' + show_poster['posters'][0]['file_path']
        except (IndexError,TypeError):
            pass

    # Download the poster and update the database
    if fetch_poster == True:
        if url and download_poster(url):
            url=os.path.basename(url)
        else:
            url=None

    # Create the show object
    if g.show_type == "movies":

        # Set date to None if the string is empty
        if len(show['release_date']) == 0:
            show['release_date']=None;

        # Fetch the director form the casting
        director=""
        for cur_guy in show['credits']['crew']:
            if cur_guy['job'] == "Director":
                director+=cur_guy["name"] + " / "

        # Remove the last slash if it exists
        director=director.rstrip(' / ')

        if director == "":
            director="Inconnu"

        # Create the object
        show_obj=Movie(name=show['title'],
            release_date=show['release_date'],
            original_name=show['original_title'],
            url=os.path.join(app.config['TMVDB_BASE_URL'],"movie",str(id)),
            tmvdb_id=id,
            poster_path=url,
            director=director,
            overview=show['overview'],
            duration=show['runtime'])

    elif g.show_type == "tvshows":

        # Generate the showruners string
        showrunner=""
        for cur_guy in show['created_by']:
                showrunner+=cur_guy["name"] + " / "

        # Remove the last slash if it exists
        showrunner=showrunner.rstrip(' / ')

        if showrunner == "":
            showrunner="Inconnu"

        # Create the object
        show_obj=TVShow(name=show['name'],
            release_date=show['first_air_date'],
            original_name=show['original_name'],
            url=os.path.join(app.config['TMVDB_BASE_URL'],"tv",str(id)),
            tmvdb_id=id,
            poster_path=url,
            director=showrunner,
            overview=show['overview'],
            nb_seasons=show['number_of_seasons'])
    else:
        return None

    return show_obj

def search_page_number(query):
    """
        Function that returns how many result page we're going to handle for a specific query
    """

    # Local variables
    languages_list=["fr"]

    # Query the API using the query in parameter
    for cur_language in languages_list:
        app.logger.info("URL de recherche: %s" % os.path.join(app.config['API_URL'],("search/" + tmvdb_mode[g.show_type] + "?api_key=" + app.config['API_KEY'] + "&language=" + cur_language + "&query=" + urllib.parse.quote(query.encode('utf-8')))))
        result=tmvdb_connect(os.path.join(app.config['API_URL'],("search/" + tmvdb_mode[g.show_type] + "?api_key=" + app.config['API_KEY'] + "&language=" + cur_language + "&query=" + urllib.parse.quote(query.encode('utf-8')))))

    # Return the page number if we have someone to return
    if result != None:
        return result["total_pages"]
    else:
        return -1

if __name__ == "__main__":
    test=search_shows("tuche")
    for cur_test in test:
        print(cur_test)

    show=get_show(550)
    print(show.name)
    print(show.director)
    print(show.release_date)
    print(show.poster_path)
