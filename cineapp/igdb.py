# -*- coding: utf-8 -*-
from __future__ import print_function
from builtins import str
import json, os, time, requests, deepl
from datetime import datetime
from igdb.wrapper import IGDBWrapper
from sqlalchemy.orm.attributes import set_committed_value
from cineapp.models import VideoGame, Region
from flask import current_app as app, flash

# Wrapper cache
_wrapper_cache = {
    "wrapper": None,
    "expires_at": 0
}

def _get_wrapper():
    """
        Get an IGDBWrapper instance, handling Twitch OAuth2 authentication with caching
    """
    now = time.time()
    if _wrapper_cache["wrapper"] and now < _wrapper_cache["expires_at"]:
        return _wrapper_cache["wrapper"]

    client_id = app.config.get("IGDB_CLIENT_ID", "")
    client_secret = app.config.get("IGDB_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        app.logger.error("IGDB_CLIENT_ID ou IGDB_CLIENT_SECRET non configuré")
        return None

    # Authenticate with Twitch OAuth2
    resp = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    })

    if resp.status_code != 200:
        app.logger.error("Erreur d'authentification IGDB: %s", resp.text)
        return None

    data = resp.json()
    access_token = data["access_token"]

    _wrapper_cache["wrapper"] = IGDBWrapper(client_id, access_token)
    _wrapper_cache["expires_at"] = now + data.get("expires_in", 3600) - 60

    return _wrapper_cache["wrapper"]

def _igdb_request(endpoint, body):
    """
        Internal function to query the IGDB API using the official wrapper
    """
    wrapper = _get_wrapper()
    if not wrapper:
        return None

    app.logger.debug("IGDB request: %s - %s", endpoint, body)

    try:
        byte_array = wrapper.api_request(endpoint, body)
        return json.loads(byte_array)
    except requests.HTTPError as e:
        app.logger.error("Erreur IGDB: %s", e)
        return None
    except Exception as e:
        app.logger.error("Exception IGDB: %s", e)
        return None


def _translate(text):
    """
        Translate text using DeepL API to the configured target language.
        Returns a tuple (translated_text, success_flag).
    """
    if not text:
        return text, False

    api_key = app.config.get("DEEPL_API_KEY", "")
    target_lang = app.config.get("DEEPL_TARGET_LANG", "FR")

    try:
        translator = deepl.Translator(api_key)
        result = translator.translate_text(text, target_lang=target_lang)
        return result.text, True
    except Exception as e:
        app.logger.error("Erreur de traduction DeepL: [%s] %s", type(e).__name__, e)
        return text, False


IGDB_PAGE_SIZE = 20

def search_games(query, page=1):

    """
        Search games on IGDB, return a list of VideoGame objects
    """

    offset = (page - 1) * IGDB_PAGE_SIZE
    body = 'search "%s"; fields name,cover.url,first_release_date,involved_companies.company.name,involved_companies.developer,involved_companies.publisher,platforms.name; limit %d; offset %d;' % (query.replace('"', '\\"'), IGDB_PAGE_SIZE, offset)

    results = _igdb_request("games", body)
    if results is None:
        return []

    games_list = []
    for game in results:
        # Extract year
        release_date = None
        if "first_release_date" in game and game["first_release_date"]:
            try:
                release_date = datetime.utcfromtimestamp(game["first_release_date"]).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass

        # Extract platforms
        platforms = ""
        if "platforms" in game and game["platforms"]:
            platform_names = []
            for p in game["platforms"]:
                if isinstance(p, dict) and "name" in p:
                    platform_names.append(p["name"])
            platforms = ", ".join(platform_names)

        # Extract developer
        developer = ""
        if "involved_companies" in game and game["involved_companies"]:
            devs = []
            for ic in game["involved_companies"]:
                if isinstance(ic, dict) and ic.get("developer") and "company" in ic:
                    company = ic["company"]
                    if isinstance(company, dict) and "name" in company:
                        devs.append(company["name"])
            developer = " / ".join(devs) if devs else "Inconnu"

        if not developer:
            developer = "Inconnu"

        # Build cover URL for display
        poster_path = None
        if "cover" in game and game["cover"] and isinstance(game["cover"], dict):
            cover_url = game["cover"].get("url")
            if cover_url:
                poster_path = "https:" + cover_url.replace("t_thumb", "t_cover_big")

        game_obj = VideoGame(
            name=game.get("name", "Inconnu"),
            release_date=release_date,
            director=developer,
            external_id=game.get("id"),
            platforms=platforms,
            poster_path=poster_path
        )

        games_list.append(game_obj)

    return games_list


def get_game(external_id):
    """
        Get full game details from IGDB
    """

    body = 'fields name,summary,cover.url,first_release_date,involved_companies.company.name,involved_companies.developer,involved_companies.publisher,platforms.name,url,alternative_names.name,alternative_names.comment,release_dates.date,release_dates.region,release_dates.release_region.region,release_dates.platform.name,game_localizations.cover.url,game_localizations.region; where id = %s;' % str(external_id)

    results = _igdb_request("games", body)
    if not results or len(results) == 0:
        app.logger.error("Pas de réponse de l'API IGDB pour l'id %s", external_id)
        return None
    
    game = results[0]

    # Get the first release date and add additionnal details related to this first release date (Country and Platforms)
    first_ts = game.get("first_release_date")
    release_date = None
    if first_ts:
        try:
            release_date = datetime.utcfromtimestamp(first_ts).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass

    # First, let's find regions that have the same release date than the first release date
    matching_region_ids=[]
    for rd in game.get("release_dates", []) or []:
        if rd.get("date") == first_ts:
            matching_region_ids.append(rd)
        
    # Identify the region we're going to store in database with the attached platforms
    selected_release_region = None
    selected_region_obj = None
    release_platform_string = ""
    if matching_region_ids:

        # Let's fetch the region by higher priorities
        regions_list = Region.query.order_by(Region.priority.desc()).all()

        for cur_region in regions_list:
            for cur_matching_region in matching_region_ids:
                if cur_region.id == cur_matching_region.get("release_region").get("id"):

                    # We found the region for which one we're going to fetch details
                    selected_release_region = cur_region.id
                    selected_region_obj = cur_region

        # Now we have a region defined by the priority, find the platforms linked to that date and region 
        release_platform_list = []
        for cur_matching_region in matching_region_ids:
            if selected_release_region == cur_matching_region.get("release_region").get("id"):
                release_platform_list.append(cur_matching_region.get("platform").get("name"))

        release_platform_string = ", ".join(release_platform_list)
                       
    # Fill the platform lists for which the game has been released on
    platforms = ""
    if "platforms" in game and game["platforms"]:
        platform_names = []
        for p in game["platforms"]:
            if isinstance(p, dict) and "name" in p:
                platform_names.append(p["name"])
        platforms = ", ".join(platform_names)

    # Populate developer and publisher fields
    developer = ""
    publisher = ""
    if "involved_companies" in game and game["involved_companies"]:
        devs = []
        pubs = []
        for ic in game["involved_companies"]:
            if isinstance(ic, dict) and "company" in ic:
                company = ic["company"]
                company_name = company.get("name", "") if isinstance(company, dict) else ""
                if company_name:
                    if ic.get("developer"):
                        devs.append(company_name)
                    if ic.get("publisher"):
                        pubs.append(company_name)
        developer = " / ".join(devs) if devs else "Inconnu"
        publisher = " / ".join(pubs) if pubs else "Inconnu"

    if not developer:
        developer = "Inconnu"
    if not publisher:
        publisher = "Inconnu"

    cover_url = None

    # Let's fetch the region by higher priorities
    regions_list = Region.query.order_by(Region.priority.desc()).all()

    for cur_cover in game.get("game_localizations", []) or []:
        for cur_region in regions_list:
                if cover_url == None and cur_region.id == cur_cover.get("region"):
                    try:
                        cover_url=cur_cover.get("cover").get("url")
                        break
                    except AttributeError as ae:
                        app.logger.error("No cover available for that region")
                        pass
                    
        if cover_url != None:
            break

    if not cover_url and isinstance(game.get("cover"), dict):
        cover_url = game.get("cover").get("url")

    poster_path = None
    if cover_url:
        cover_url = "https:" + cover_url.replace("t_thumb", "t_cover_big")
        if download_poster(cover_url):
            poster_path = os.path.basename(cover_url)

    # Look for a French alternative title
    original_name = game.get("name")
    display_name = original_name
    for alt in game.get("alternative_names", []) or []:
        comment = (alt.get("comment") or "").lower()
        if "french" in comment or "france" in comment or "français" in comment or comment.strip() == "fr":
            display_name = alt.get("name") or display_name
            break

    # Translate overview
    translated_overview, overview_translated = _translate(game.get("summary", ""))

    # IGDB URL
    url = game.get("url")

    game_obj = VideoGame(
        name=display_name,
        release_date=release_date,
        original_name=original_name,
        url=url,
        external_id=external_id,
        poster_path=poster_path,
        director=developer,
        overview=translated_overview,
        overview_translated=overview_translated,
        platforms=platforms,
        publisher=publisher,
        release_region_id=selected_release_region,
        release_platform=release_platform_string
    )

    # Bind the Region on this transient preview without firing the backref
    # event (would dirty Region.videogames and trigger SAWarning on next autoflush).
    set_committed_value(game_obj, 'release_region', selected_region_obj)

    return game_obj


def download_poster(url):
    """
        Download a cover image from IGDB
    """
    try:
        resp = requests.get(url)
        if resp.status_code != 200:
            return False

        local_path = os.path.join(app.config['POSTERS_PATH'], os.path.basename(url))
        with open(local_path, 'wb') as f:
            f.write(resp.content)
        return True

    except Exception as e:
        app.logger.error("Erreur téléchargement poster IGDB: %s", e)
        return False


def search_page_number(query):
    """
        Function that returns how many result pages we're going to handle for a specific query
    """
    import math
    body = 'search "%s";' % query.replace('"', '\\"')

    result = _igdb_request("games/count", body)
    if result is None or "count" not in result:
        return 1

    total = result["count"]
    if total == 0:
        return 1

    return math.ceil(total / IGDB_PAGE_SIZE)
