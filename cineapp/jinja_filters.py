# -*- coding: utf-8 -*-
from __future__ import print_function
from past.builtins import basestring
from cineapp import app
import datetime

@app.template_filter()
def minutes_to_human_duration(minutes_duration):
	"""
		Convert a duration in minutes into a duration in a cool format human readable
	"""
	try:
		hours,minutes = divmod(minutes_duration,60)
		return "%sh %smin" %(hours,minutes)
	except TypeError:
		return None

@app.template_filter()
def date_format(date,format_date):
	"""
		Convert a date object into a custom format
	"""
	try:
		if isinstance(date, basestring):
			date_array=date.split('-')
			date_to_convert=datetime.datetime(int(date_array[0]),int(date_array[1]),int(date_array[2]))
			return date_to_convert.strftime(format_date)
		else:
			return date.strftime(format_date)
	except Exception as e:
		print(e)
		return None
