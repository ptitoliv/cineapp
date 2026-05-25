# -*- coding: utf-8 -*-
from __future__ import division
from past.utils import old_div
from flask import current_app
from cineapp.models import db, Show, Mark, MarkComment, FavoriteShow
from sqlalchemy.sql.expression import literal, desc
from datetime import datetime
import PIL, os, re
from PIL import Image

_HUMANIZE_MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
                      "juil.", "août", "sept.", "oct.", "nov.", "déc."]

def humanize_when(dt):
    """
        Returns a short French humanized form of a datetime relative to now.
        Examples: "à l'instant", "il y a 12min", "il y a 3h", "hier · 18:04",
        "il y a 4j", "12 mars · 14:30".
    """
    if dt is None:
        return ""
    now = datetime.now()
    diff = now - dt
    seconds = diff.total_seconds()
    if seconds < 60:
        return "à l'instant"
    if seconds < 3600:
        return "il y a %dmin" % int(seconds // 60)
    if seconds < 86400:
        return "il y a %dh" % int(seconds // 3600)
    if diff.days == 1:
        return "hier · %s" % dt.strftime("%H:%M")
    if diff.days < 7:
        return "il y a %dj" % diff.days
    return "%d %s · %s" % (dt.day, _HUMANIZE_MONTHS_FR[dt.month - 1], dt.strftime("%H:%M"))

def frange(start, end, step):
    tmp = start
    while(tmp <= end):
        yield tmp
        tmp += step

def get_activity_list(start, length, show_type):

    """
        Returns an array containing activity records ordered by descending date
        Params are a range of records we want to have in the returned array
    """

    # Object_items
    object_dict={"count": 0, "list": []}
    object_list=[]

    # Show Query
    shows_query=db.session.query(Show.id.label("id"),literal("user_id").label("user_id"),Show.added_when.label("entry_date"),literal("shows").label("entry_type")).filter(Show.show_type==show_type)

    # Marks Query
    marks_query=db.session.query(Mark.show_id.label("id"),Mark.user_id.label("user_id"),Mark.updated_when.label("entry_date"),literal("marks").label("entry_type")).join(Show).filter(Mark.mark != None).filter(Show.show_type==show_type)

    # Homework Query
    homework_query=db.session.query(Mark.show_id.label("id"),Mark.user_id.label("user_id"),Mark.homework_when.label("entry_date"),literal("homeworks").label("entry_type")).join(Show).filter(Mark.homework_when != None).filter(Show.show_type==show_type)

    # Comment Query
    comment_query=db.session.query(MarkComment.markcomment_id.label("id"),MarkComment.user_id.label("user_id"),MarkComment.posted_when.label("entry_date"),literal("comments").label("entry_type")).join(Mark).join(Show).filter(Show.show_type==show_type)

    # Favorite Query
    favorite_query=db.session.query(FavoriteShow.show_id.label("id"),FavoriteShow.user_id.label("user_id"),FavoriteShow.added_when.label("entry_date"),literal("favorites").label("entry_type")).join(Show).filter(Show.show_type==show_type).filter(FavoriteShow.deleted_when == None)

    # Build the union request
    activity_list = shows_query.union(marks_query,homework_query,comment_query,favorite_query).order_by(desc("entry_date")).slice(int(start),int(start) + int(length))

    for cur_item in activity_list:
        if cur_item.entry_type == "shows":
            object_list.append({"entry_type": "shows", "object" : Show.query.get(cur_item.id)})
        elif cur_item.entry_type == "marks":
            object_list.append({"entry_type": "marks", "object" : Mark.query.get((cur_item.user_id,cur_item.id))})
        elif cur_item.entry_type == "homeworks":
            object_list.append({"entry_type" : "homeworks", "object" : Mark.query.get((cur_item.user_id,cur_item.id))}) 
        elif cur_item.entry_type == "comments":
            object_list.append({"entry_type" : "comments", "object" : MarkComment.query.get((cur_item.id))}) 
        elif cur_item.entry_type == "favorites":
            object_list.append({"entry_type": "favorites", "object" : FavoriteShow.query.get((cur_item.id,cur_item.user_id))})

    # Count activity number (Will be used for the datatable pagination)
    object_dict["count"]=shows_query.union(marks_query,homework_query).order_by(desc("entry_date")).count()
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
        img = img.resize((basewidth, hsize), PIL.Image.LANCZOS)

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

def fts_boolean_query(raw):
    """
        Turn a user-supplied search string into a MariaDB FTS boolean-mode
        query with implicit AND: each token becomes mandatory ('+token').
        Tokens shorter than 3 chars are dropped (innodb_ft_min_token_size=3)
        and FTS-reserved operators (+, -, *, ", (, ), ~, @, <, >) are stripped.
    """
    tokens = [t for t in re.findall(r'\w+', raw or '', flags=re.UNICODE) if len(t) >= 3]
    return ' '.join('+%s' % t for t in tokens)
