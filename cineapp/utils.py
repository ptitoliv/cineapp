# -*- coding: utf-8 -*-
from __future__ import division
from past.utils import old_div
from flask import current_app
from cineapp.models import db, Show, Mark, MarkComment, FavoriteShow
from sqlalchemy.sql.expression import literal, desc
from datetime import datetime
import PIL, os, re, nh3, html2text
from PIL import Image

_HUMANIZE_MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
                      "juil.", "août", "sept.", "oct.", "nov.", "déc."]

# Tags the CKEditor5 toolbar (Bold / Italic / Font / List) can legitimately
# emit. Everything else — and every attribute except a span's inline style
# (used by the Font color/size/family features) — is stripped.
_COMMENT_ALLOWED_TAGS = {"p", "br", "strong", "b", "i", "em", "u", "s",
                         "ul", "ol", "li", "span"}
_COMMENT_ALLOWED_ATTRS = {"span": {"style"}}

def sanitize_comment(html):
    """
        Server-side sanitization of a CKEditor-authored rating comment.
        CKEditor only runs in the browser, so any HTTP client can POST
        arbitrary markup; we strip everything outside a small formatting
        allow-list before the value is stored and later rendered with `|safe`
        (display_show.html) or injected raw into the activity feed
        (activity_flow.js). Prevents stored XSS (CWE-79).
    """
    return nh3.clean(html, tags=_COMMENT_ALLOWED_TAGS,
                     attributes=_COMMENT_ALLOWED_ATTRS)

def html_to_markdown(html):
    """
        Convert a CKEditor-authored (HTML) rating comment to lightweight markup
        that reads cleanly as plain text. Shared by the Slack notifications
        (slack.py) and the plain-text e-mails (emails.py).

        The comment is stored as HTML (see sanitize_comment). Rendered raw it
        showed literal tags and broke the layout, so we run it through html2text
        configured for a Slack-flavoured dialect that doubles as readable plain
        text: *bold*, _italic_, • bullets, no hard line-wrapping. Plain-text
        (tag-less) legacy comments pass through unchanged.
    """
    h = html2text.HTML2Text()
    h.body_width = 0          # no hard-wrapping
    h.strong_mark = "*"       # bold
    h.emphasis_mark = "_"     # italic
    h.ul_item_mark = "•"
    h.ignore_links = True
    h.ignore_images = True
    text = h.handle(html or "")
    # html2text pads block boundaries with extra blank lines and marks hard
    # breaks with trailing spaces — normalise both so the quote reads clean.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # html2text leaves a stray space between a closing emphasis marker and
    # trailing punctuation ("_sublime_ ," from "<u>sublime</u>,"). Drop it,
    # but only before punctuation that takes no leading space in French
    # (. , ) ] }) so correct French spacing before : ; ! ? stays untouched.
    text = re.sub(r"([*_~])[ \t]+([.,)\]}])", r"\1\2", text)
    return text.strip()

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
    activity_list = shows_query.union(marks_query,homework_query,comment_query,favorite_query).order_by(desc("entry_date"),"entry_type","id","user_id").slice(int(start),int(start) + int(length))

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
    object_dict["count"]=shows_query.union(marks_query,homework_query,comment_query,favorite_query).count()
    object_dict["list"]=object_list

    # Return the filled object
    return object_dict

def avatar_url(user):
    """
        Single source of truth for a user's avatar image URL. Returns the full
        URL (AVATARS_URL + stored filename) or None when the user has no avatar,
        so both Python payloads and templates build the URL the same way.
        Exposed to Jinja as a global in create_app.
    """
    if user is None or not user.avatar:
        return None
    return current_app.config['AVATARS_URL'] + user.avatar

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

_ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG"}

def is_allowed_image(fp):
    """
        True if `fp` (a file-like object) decodes as an image of an allowed
        format. Validates the REAL content via Pillow instead of trusting a
        client-supplied Content-Type (avatar upload) or a remote API response
        (poster download). `img.load()` forces decoding so truncated / garbage
        payloads are rejected, not just mislabelled ones (CWE-434 hardening).
    """
    try:
        with Image.open(fp) as img:
            fmt = img.format
            img.load()
        return fmt in _ALLOWED_IMAGE_FORMATS
    except Exception:
        return False

# MariaDB/InnoDB default fulltext stopwords. A mandatory '+stopword' never
# matches (stopwords are not indexed), so keeping one would make a search like
# "The Last of Us" return nothing. Mirrors information_schema.INNODB_FT_DEFAULT_STOPWORD.
FTS_STOPWORDS = frozenset({
    'a', 'about', 'an', 'are', 'as', 'at', 'be', 'by', 'com', 'de', 'en',
    'for', 'from', 'how', 'i', 'in', 'is', 'it', 'la', 'of', 'on', 'or',
    'that', 'the', 'this', 'to', 'was', 'what', 'when', 'where', 'who',
    'will', 'with', 'und', 'www',
})

def fts_boolean_query(raw):
    """
        Turn a user-supplied search string into a MariaDB FTS boolean-mode
        query with implicit AND: each token becomes mandatory ('+token').
        Tokens shorter than 3 chars are dropped (innodb_ft_min_token_size=3),
        InnoDB fulltext stopwords are dropped (a mandatory '+stopword' never
        matches), and FTS-reserved operators (+, -, *, ", (, ), ~, @, <, >) are
        stripped.
    """
    tokens = [t for t in re.findall(r'\w+', raw or '', flags=re.UNICODE)
              if len(t) >= 3 and t.lower() not in FTS_STOPWORDS]
    return ' '.join('+%s' % t for t in tokens)
