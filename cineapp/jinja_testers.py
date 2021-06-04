from cineapp import app
from cineapp.models import Movie, TVShow

@app.template_test()
def movie(obj):
        if type(obj) is Movie:
                return True
        else:
                return False


@app.template_test()
def tvshow(obj):
        if type(obj) is TVShow:
                return True
        else:
                return False
