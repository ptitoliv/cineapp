# -*- coding: utf-8 -*-

from wtforms import fields, widgets
from flask import Markup

# Define wtforms widget and field
class CKTextAreaWidget(widgets.TextArea):
	def __call__(self, field, **kwargs):
		kwargs.setdefault('class_', 'ckeditor')
		html_string = super(CKTextAreaWidget, self).__call__(field, **kwargs)
		html_string += Markup(("""<script>
			CKEDITOR.replace( '%s', {
				enterMode: CKEDITOR.ENTER_BR
		        } );	
			</script>""" % field.id))
		return widgets.HTMLString(html_string)

class CKTextAreaField(fields.TextAreaField):
	widget = CKTextAreaWidget()

# Widget which returns a complete search bar with a glyphicon button
class SearchButtonWidget(widgets.SubmitInput):

    html_params = staticmethod(widgets.html_params)
    input_type = 'submit'

    def __call__(self, field, **kwargs):
        kwargs.setdefault('id', field.id)
        kwargs.setdefault('type', self.input_type)
        kwargs.setdefault('value', field.label.text)

        if 'value' not in kwargs:
            kwargs['value'] = field._value()

        return widgets.HTMLString('<button %s><i class="glyphicon glyphicon-search"></i></button>' % self.html_params(name=field.name, **kwargs))

# SearchButtonField used for display the previous widget
class SearchButtonField(fields.BooleanField):
	widget = SearchButtonWidget()
