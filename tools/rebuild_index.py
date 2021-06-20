#!/usr/bin/env python

import datetime
from flask_msearch import Search
from cineapp import app
from cineapp import models

search = Search()
search.init_app(app)

search.create_index(models.Movie)
search.create_index(models.TVShow)
