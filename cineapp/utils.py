# -*- coding: utf-8 -*-
from __future__ import division
from past.utils import old_div
from cineapp import db
from cineapp.models import Movie, Mark, MarkComment, FavoriteMovie
from sqlalchemy.sql.expression import literal, desc
import PIL, os
from PIL import Image

def frange(start, end, step):
	tmp = start
	while(tmp <= end):
		yield tmp
		tmp += step

def get_activity_list(start, length):

	"""
		Returns an array containing activity records ordered by descending date
		Params are a range of records we want to have in the returned array
	"""

	# Object_items
	object_dict={"count": 0, "list": []}
	object_list=[]
	
	# Movie Query
	movies_query=db.session.query(Movie.id.label("id"),literal("user_id").label("user_id"),Movie.added_when.label("entry_date"),literal("movies").label("entry_type"))

	# Marks Query
	marks_query=db.session.query(Mark.movie_id.label("id"),Mark.user_id.label("user_id"),Mark.updated_when.label("entry_date"),literal("marks").label("entry_type")).filter(Mark.mark != None)

	# Homework Query
	homework_query=db.session.query(Mark.movie_id.label("id"),Mark.user_id.label("user_id"),Mark.homework_when.label("entry_date"),literal("homeworks").label("entry_type")).filter(Mark.homework_when != None)

	# Comment Query
	comment_query=db.session.query(MarkComment.markcomment_id.label("id"),MarkComment.user_id.label("user_id"),MarkComment.posted_when.label("entry_date"),literal("comments").label("entry_type"))

	# Favorite Query
	favorite_query=db.session.query(FavoriteMovie.movie_id.label("id"),FavoriteMovie.user_id.label("user_id"),FavoriteMovie.added_when.label("entry_date"),literal("favorites").label("entry_type")).filter(FavoriteMovie.deleted_when == None)

	# Build the union request
	activity_list = movies_query.union(marks_query,homework_query,comment_query,favorite_query).order_by(desc("entry_date")).slice(int(start),int(start) + int(length))

	for cur_item in activity_list:
		if cur_item.entry_type == "movies":
			object_list.append({"entry_type": "movies", "object" : Movie.query.get(cur_item.id)})
		elif cur_item.entry_type == "marks":
			object_list.append({"entry_type": "marks", "object" : Mark.query.get((cur_item.user_id,cur_item.id))})
		elif cur_item.entry_type == "homeworks":
			object_list.append({"entry_type" : "homeworks", "object" : Mark.query.get((cur_item.user_id,cur_item.id))}) 
		elif cur_item.entry_type == "comments":
			object_list.append({"entry_type" : "comments", "object" : MarkComment.query.get((cur_item.id))}) 
		elif cur_item.entry_type == "favorites":
			object_list.append({"entry_type": "favorites", "object" : FavoriteMovie.query.get((cur_item.id,cur_item.user_id))})

	# Count activity number (Will be used for the datatable pagination)
	object_dict["count"]=movies_query.union(marks_query,homework_query).order_by(desc("entry_date")).count()
	object_dict["list"]=object_list

	# Return the filled object
	return object_dict

def resize_avatar(avatar_path):

	""" 
		Function that resizes the uploaded avatar to a correct avatar size
	"""
	try:
		basewidth = 200
		img = Image.open(avatar_path)

		# Resize the image
		wpercent = (basewidth / float(img.size[0]))
		hsize = int((float(img.size[1]) * float(wpercent)))
		img = img.resize((basewidth, hsize), PIL.Image.ANTIALIAS)

		# And then we crop
		half_the_width = old_div(img.size[0], 2)
		half_the_height = old_div(img.size[1], 2)
		img = img.crop( ( half_the_width - ( old_div(basewidth,2) ),
				half_the_height - ( old_div(basewidth,2) ),
				half_the_width + ( old_div(basewidth,2) ),
				half_the_height + ( old_div(basewidth,2) ) )
			)
			
		# Save the image
		img.save(avatar_path + '.png')
		
		# Rename the image
		os.rename(avatar_path + '.png',avatar_path)

		# Return true
		return True
	except Exception as e:

		# Try to remove the temporary picture if it exists
		if os.path.isfile(avatar_path + '.png'):
			os.remove(avatar_path + '.png')

		return False
