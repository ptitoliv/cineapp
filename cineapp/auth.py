# -*- coding: utf-8 -*-

from functools import wraps
from flask.ext.login import current_user
from flask import flash, redirect, url_for

def guest_control(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if current_user.is_guest == True:
		flash("Accès interdit pour les invités","danger")
		return redirect(url_for('list_movies'))
        return func(*args, **kwargs)
    return decorated_view
