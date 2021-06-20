# -*- coding: utf-8 -*-

from builtins import next
import urllib.request, urllib.parse, urllib.error, re, locale, json, copy, html2text, hashlib, time, os
from datetime import datetime
from flask import render_template, flash, redirect, url_for, g, request, session, abort, Blueprint
from flask_login import login_user, logout_user, current_user, login_required
from flask_wtf import Form
from cineapp import app, db, lm
from cineapp.models import User, Show, Mark, Origin, Type, FavoriteShow, FavoriteType, PushNotification, Movie, TVShow
from cineapp.utils import frange, get_activity_list, resize_avatar
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm.exc import FlushError
from sqlalchemy import desc, or_, and_, Table, text
from sqlalchemy.sql.expression import select, case, literal
from bcrypt import hashpw, gensalt
from werkzeug.utils import secure_filename
from random import randint
from cineapp.auth import guest_control
from cineapp.messages import tvshow_messages, movie_messages

graph_bp = Blueprint('graphs',__name__,url_prefix='/graph')

@graph_bp.route('/mark', endpoint="graph_by_mark")
@graph_bp.route('/mark_percent', endpoint="graph_by_mark_percent")
@graph_bp.route('/mark_interval', endpoint="graph_by_mark_interval")
@graph_bp.route('/type', endpoint="graph_by_type")
@graph_bp.route('/origin', endpoint="graph_by_origin")
@graph_bp.route('/year', endpoint="graph_by_year")
@graph_bp.route('/year_theater', endpoint="graph_by_year_theater")
@graph_bp.route('/average_type', endpoint="average_by_type")
@graph_bp.route('/average_origin', endpoint="average_by_origin")
@graph_bp.route('/average_by_year', endpoint="average_by_year")
@login_required
@guest_control
def show_graphs():

        # Retrieve the graph_list from the app context and use it in a local variable
        graph_list = app.config['GRAPH_LIST']

        # Identify prev and next graph
        for index_graph in range(len(graph_list)):
            if request.endpoint == graph_list[index_graph]["graph_endpoint"]: 
                    
                        # Check if the graph must be displayed
                        if graph_list[index_graph][g.show_type]==False:
                            app.logger.info("Le graphe %s n'est pas autorisé dans le mode %s" % (request.endpoint,g.show_type))
                            abort(404)

                        # Set the graph_title
                        graph_title=graph_list[index_graph]["graph_label"]
        
                        # Set the graph pagination
                        if index_graph - 1 >= 0:

                                # We display only link for graph we want to display
                                # We check if the previous graph has to be displayed considering the mode
                                # If yes we display it, if not we use the previous one until the begenning on the list
                                temp_index_graph=index_graph
                                while graph_list[temp_index_graph-1][g.show_type]==False:
                                    temp_index_graph=temp_index_graph-1

                                # If we reach the begenning of the list then set the prev_graph to none
                                if temp_index_graph-1 >= 0:
                                    prev_graph=graph_list[temp_index_graph-1]
                                else:
                                    prev_graph=None
                        else:
                                prev_graph=None

                        if index_graph + 1 < len(graph_list):

                                # We display only link for graph we want to display
                                # We check if then next graph has to be displayed considering the mode
                                # If yes we display it, if not we use the next one until the end of the list

                                temp_index_graph=index_graph
                                while graph_list[temp_index_graph+1][g.show_type]==False:
                                    temp_index_graph=temp_index_graph+1

                                # If we reach the begenning of the list then set the prev_graph to none
                                if temp_index_graph+1 <= len(graph_list):
                                    next_graph=graph_list[temp_index_graph+1]
                                else:
                                    next_graph=None
                        else:
                                next_graph=None

                        # We found a graph ==> Stop the main loop
                        break;

        # Generate the correct data considering the route
        graph_to_generate=os.path.basename(request.url_rule.rule)

        # Variable initialization
        labels=[]
        data={}

        # Define the base query for queries where we can use it
        # For some we will use the show_type filter
        if g.show_type == "movie": 
            basequery = Mark.query.join(Movie)
        elif g.show_type == "tvshow": 
            basequery = Mark.query.join(TVShow)

        # Fetch all users
        users = User.query.all();

        if graph_to_generate == "mark":
                
                # Distributed marks graph
                graph_type="line"

                for cur_mark in frange(0,20,0.5):
                        labels.append(cur_mark)

                # Fill the dictionnary with distributed_marks by user
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
                        for cur_mark in frange(0,20,0.5):
                                data[cur_user.nickname]["data"].append(basequery.filter(Mark.mark==cur_mark,Mark.user_id==cur_user.id).count())

        if graph_to_generate == "mark_interval":

                range_mark_array=[]
                
                # Distributed marks graph
                graph_type="line"

                for cur_mark in frange(0,20,0.5):
                        range_mark_array.append(cur_mark)
        
                # Fille the label array
                for cur_index in range(0,len(range_mark_array)):
                        if cur_index < len(range_mark_array)-1:
                                labels.append(str(range_mark_array[cur_index]) + " - " + str(range_mark_array[cur_index+1]))
                        else:
                                labels.append(str(range_mark_array[cur_index]))

                # Fill the dictionnary with distributed_marks by user
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
                        for cur_index in range(0,len(range_mark_array)):
                                if cur_index < len(range_mark_array)-1:
                                        data[cur_user.nickname]["data"].append(basequery.filter(Mark.mark>=range_mark_array[cur_index],Mark.mark<range_mark_array[cur_index+1],Mark.user_id==cur_user.id).count())
                                else:
                                        data[cur_user.nickname]["data"].append(basequery.filter(Mark.mark>=range_mark_array[cur_index],Mark.user_id==cur_user.id).count())

        if graph_to_generate == "mark_percent":
                
                # Distributed marks graph
                graph_type="line"

                # Fill the labels_array with all marks possible
                for cur_mark in frange(0,20,0.5):
                        labels.append(cur_mark)

                # Fill the dictionnary with distributed_marks by user
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }

                        # Set the percentage considering the total shows number seen for each user and not globally
                        user_shows_count = basequery.filter(Mark.user_id==cur_user.id).count()

                        if user_shows_count != 0:
                            for cur_mark in frange(0,20,0.5):
                                    percent = float((basequery.filter(Mark.mark==cur_mark,Mark.user_id==cur_user.id).count() * 100)) / float(user_shows_count)
                                    data[cur_user.nickname]["data"].append(round(percent,2))

        elif graph_to_generate == "type":

                # Distributed types graph
                graph_type="bar"

                # Fill the types_array with all the types stored into the database
                types = Type.query.all();
                for cur_type in types:
                        labels.append(cur_type.type)

                # Fill the dictionnary with distributed_types by user
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
                        for cur_type in types:
                                data[cur_user.nickname]["data"].append(basequery.filter(Mark.mark!=None,Mark.user_id==cur_user.id,Show.type==cur_type.id).count())
        
        elif graph_to_generate == "origin":

                # Distributed marks graph
                graph_type="bar"

                # Fill the origin_array with all the types stored into the database
                origins = Origin.query.all();
                for cur_origin in origins:
                        labels.append(cur_origin.origin)

                # Fill the dictionnary with distributed_origins by user
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
                        for cur_origin in origins:
                                data[cur_user.nickname]["data"].append(basequery.filter(Mark.mark!=None,Mark.user_id==cur_user.id,Show.origin==cur_origin.id).count())


        elif graph_to_generate == "average_type":

                # Average by type
                graph_type="radar"

                # Fill the types array with all the types stored into the database
                types = Type.query.all();
                for cur_type in types:
                        labels.append(cur_type.type)

                # Fill the dictionnary with average mark by user and by type
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
                        for cur_type in types:
                                avg_query=db.session.query(db.func.avg(Mark.mark).label("average")).join(Show).filter(Show.show_type==g.show_type).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Show.type==cur_type.id).one()
                                
                                # If no mark => Put null
                                if avg_query.average == None:
                                        data[cur_user.nickname]["data"].append("null")
                                else:
                                        data[cur_user.nickname]["data"].append(round(float(avg_query.average),2))

        elif graph_to_generate == "average_origin":

                # Average by type
                graph_type="radar"

                # Fill the origins array with all the origins stored into the database
                origins = Origin.query.all();
                for cur_origin in origins:
                        labels.append(cur_origin.origin)

                # Fill the dictionnary with average mark by user and by type
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : [] }
                        for cur_origin in origins:
                                avg_query=db.session.query(db.func.avg(Mark.mark).label("average")).join(Show).filter(Show.show_type==g.show_type).filter(Mark.mark!=None,Mark.user_id==cur_user.id,Show.origin==cur_origin.id).one()
                                
                                # If no mark => Put null
                                if avg_query.average == None:
                                        data[cur_user.nickname]["data"].append("null")
                                else:
                                        data[cur_user.nickname]["data"].append(round(float(avg_query.average),2))

        elif graph_to_generate == "year":

                # Distributed shows graph by year
                graph_type="line"

                # Search the min and max year in order to generate a optimized graph
                min_year=int(db.session.query(db.func.min(Mark.seen_when).label("min_year")).join(Show).filter(Show.show_type==g.show_type).one().min_year.strftime("%Y"))
                max_year=int(db.session.query(db.func.max(Mark.seen_when).label("max_year")).join(Show).filter(Show.show_type==g.show_type).one().max_year.strftime("%Y"))

                for cur_year in range(min_year,max_year+1,1):
                        labels.append(cur_year)

                # Fill the dictionnary with distributed_years by user
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : []}
                        for cur_year in range(min_year,max_year+1,1):
                                data[cur_user.nickname]["data"].append(basequery.filter(Mark.mark!=None,Mark.user_id==cur_user.id,db.func.year(Mark.seen_when)==cur_year).count())

        elif graph_to_generate == "year_theater":

                # Distributed movies graph by year
                graph_type="line"

                # Search the min and max year in order to generate a optimized graph
                min_year=int(db.session.query(db.func.min(Mark.seen_when).label("min_year")).join(Show).filter(Show.show_type==g.show_type).one().min_year.strftime("%Y"))
                max_year=int(db.session.query(db.func.max(Mark.seen_when).label("max_year")).join(Show).filter(Show.show_type==g.show_type).one().max_year.strftime("%Y"))

                for cur_year in range(min_year,max_year+1,1):
                        labels.append(cur_year)

                # Fill the dictionnary with distributed_years by user
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : []}
                        for cur_year in range(min_year,max_year+1,1):
                                data[cur_user.nickname]["data"].append(basequery.filter(Mark.mark!=None,Mark.user_id==cur_user.id,Mark.seen_where=="C",db.func.year(Mark.seen_when)==cur_year).count())

        elif graph_to_generate == "average_by_year":

                # Average by year
                graph_type="line"

                # Search the min and max year in order to generate a optimized graph
                min_year=int(db.session.query(db.func.min(Mark.seen_when).label("min_year")).join(Show).filter(Show.show_type==g.show_type).one().min_year.strftime("%Y"))
                max_year=int(db.session.query(db.func.max(Mark.seen_when).label("max_year")).join(Show).filter(Show.show_type==g.show_type).one().max_year.strftime("%Y"))

                for cur_year in range(min_year,max_year+1,1):
                        labels.append(cur_year)

                # Fill the dictionnary with average mark for each user by year
                for cur_user in users:
                        data[cur_user.nickname] = { "color" : cur_user.graph_color, "data" : []}
                        for cur_year in range(min_year,max_year+1,1):
                                avg_query=db.session.query(db.func.avg(Mark.mark).label("average")).join(Show).filter(Show.show_type==g.show_type).filter(Mark.mark!=None,Mark.user_id==cur_user.id,db.func.year(Mark.seen_when)==cur_year).one()

                                # If no mark => Put null
                                if avg_query.average == None:
                                        data[cur_user.nickname]["data"].append("null")
                                else:
                                        data[cur_user.nickname]["data"].append(round(float(avg_query.average),2))

        return render_template('show_graphs.html',graph_title=graph_title,graph_type=graph_type,labels=labels,data=data,prev_graph=prev_graph,next_graph=next_graph)

