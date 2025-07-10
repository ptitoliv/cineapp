# -*- coding: utf-8 -*-

from wtforms import fields, widgets
from markupsafe import Markup

# Define wtforms widget and field
class CKTextAreaWidget(widgets.TextArea):
    def __call__(self, field, **kwargs):
        kwargs.setdefault('class_', 'ckeditor')
        class_ = kwargs.pop('class', '') or kwargs.pop('class_', '')
        if field.data is None:
            comment_value = ""
        else:
            comment_value = field.data
        html_string = Markup(("""<script type="importmap">

            {
                "imports": {
                    "ckeditor5": "/static//ckeditor5/ckeditor5.js",
                    "ckeditor5/": "/static//ckeditor5/"
                }
            }
        </script>
        <textarea name="comment" id="%s"></textarea>
        <script type="module">
        import {
            ClassicEditor,
            Essentials,
            Paragraph,
            Bold,
            Italic,
            Font,
            List
        } from 'ckeditor5';

        ClassicEditor
        .create( document.querySelector( '#%s' ), {
            licenseKey: 'GPL', 
            plugins: [ Essentials, Paragraph, Bold, Italic, Font, List ],
            toolbar: [
                    'undo', 'redo', '|', 'bold', 'italic', '|',
                    'fontSize', 'fontFamily', 'fontColor', 'fontBackgroundColor', 'bulletedList', 'numberedList'
                ],
                initialData: "%s"
            } )
            .then( editor => {
                window.editor = editor;
            } )
            .catch( error => {
                console.error( error );
            } );
            </script>""") % (field.id, field.id,comment_value));
        return html_string

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

        return Markup('<button %s><i class="glyphicon glyphicon-search"></i></button>' % self.html_params(name=field.name, **kwargs))

# SearchButtonField used for display the previous widget
class SearchButtonField(fields.BooleanField):
    widget = SearchButtonWidget()
