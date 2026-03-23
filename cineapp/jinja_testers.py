from cineapp.models import Movie, TVShow, VideoGame

def is_movie(obj):
        if type(obj) is Movie:
                return True
        else:
                return False

def is_tvshow(obj):
        if type(obj) is TVShow:
                return True
        else:
                return False

def is_videogame(obj):
        if type(obj) is VideoGame:
                return True
        else:
                return False
