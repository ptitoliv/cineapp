# -*- coding: utf-8 -*-
from __future__ import print_function
from builtins import str
import json, os, time, requests, deepl
from datetime import datetime
from igdb.wrapper import IGDBWrapper
from cineapp.models import VideoGame
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
    if not api_key:
        app.logger.warning("DEEPL_API_KEY non configurée, pas de traduction")
        return text, False

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
    body = 'fields name,summary,cover.url,first_release_date,involved_companies.company.name,involved_companies.developer,involved_companies.publisher,platforms.name,url; where id = %s;' % str(external_id)

    results = _igdb_request("games", body)
    if not results or len(results) == 0:
        app.logger.error("Pas de réponse de l'API IGDB pour l'id %s", external_id)
        return None

    game = results[0]

    # Extract release date
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

    # Extract developer and publisher
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

    # Handle cover/poster
    poster_path = None
    if "cover" in game and game["cover"] and isinstance(game["cover"], dict):
        cover_url = game["cover"].get("url")
        if cover_url:
            cover_url = "https:" + cover_url.replace("t_thumb", "t_cover_big")
            if download_poster(cover_url):
                poster_path = os.path.basename(cover_url)
            else:
                poster_path = None

    # Translate overview
    translated_overview, overview_translated = _translate(game.get("summary", ""))

    # IGDB URL
    url = game.get("url")

    game_obj = VideoGame(
        name=game.get("name", "Inconnu"),
        release_date=release_date,
        original_name=game.get("name"),
        url=url,
        external_id=external_id,
        poster_path=poster_path,
        director=developer,
        overview=translated_overview,
        overview_translated=overview_translated,
        platforms=platforms,
        publisher=publisher
    )

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
