# -*- coding: utf-8 -*-

from functools import wraps
from flask_login import current_user
from flask import flash, redirect, url_for, g

def guest_control(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if current_user.is_guest == True:
            flash("Accès interdit pour les invités","danger")
            return redirect(url_for('show.list_shows',show_type=g.show_type))
        return func(*args, **kwargs)
    return decorated_view
