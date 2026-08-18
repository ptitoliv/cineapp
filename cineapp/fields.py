# -*- coding: utf-8 -*-

import json
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
            </script>""") % (field.id, field.id,comment_value.replace('"', '\\"')));
        return html_string

class CKTextAreaField(fields.TextAreaField):
    widget = CKTextAreaWidget()
