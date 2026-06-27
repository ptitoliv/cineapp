# -*- coding: utf-8 -*-
from __future__ import print_function
from builtins import str
import json, os, time, requests, deepl
from io import BytesIO
from datetime import datetime
from igdb.wrapper import IGDBWrapper
from sqlalchemy.orm.attributes import set_committed_value
from cineapp.models import VideoGame, VideoGameReleaseDate, Region
from cineapp.utils import is_allowed_image
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

def find_poster(game):
    """
        Select the cover URL for a game and return it as a full https URL in
        t_cover_big size (or None). The European localized cover (region id 4)
        is preferred, with a fallback to the game's main cover. Shared by
        search_games (display) and get_game (download) so both show the same cover.
    """

    cover_url = None

    # Prefer a European localized cover (Europe has id 4 in IGDB)
    for cur_cover in game.get("game_localizations", []) or []:
        region = cur_cover.get("region")
        cover = cur_cover.get("cover")
        if isinstance(region, dict) and region.get("id") == 4 and isinstance(cover, dict) and cover.get("url"):
            cover_url = cover.get("url")
            break

    # Fall back to the main cover
    if not cover_url and isinstance(game.get("cover"), dict):
        cover_url = game.get("cover").get("url")

    if not cover_url:
        return None

    return "https:" + cover_url.replace("t_thumb", "t_cover_big")


def _platforms_by_release(game):
    """
        Return the game's platform names as a comma-separated string, ordered by
        ascending release date (earliest first), using the per-platform dates in
        release_dates. Platforms with no known release date come last, keeping
        their original order. Requires release_dates.date, release_dates.platform.name
        and platforms.name in the queried fields.
    """

    # Step 1: find the earliest release date for each platform.
    # We look at every release_dates entry and, for each platform name, we keep
    # the smallest (earliest) date we have seen so far.
    # There are several release date by platform ==> Let's keep the earliest one
    
    earliest_date = {}
    for release in game.get("release_dates", []) or []:
        platform = release.get("platform")
        if not isinstance(platform, dict) or not platform.get("name"):
            continue

        platform_name = platform["name"]
        date = release.get("date")

        if platform_name not in earliest_date:
            # First time we see this platform: store its date (which may be None).
            earliest_date[platform_name] = date
        elif date is not None:
            # We already know this platform: keep the date only if it is earlier.
            known_date = earliest_date[platform_name]
            if known_date is None or date < known_date:
                earliest_date[platform_name] = date

    # Step 2: build the list of all platform names, without duplicates and
    # keeping the order in which we meet them.
    names = []
    for platform in game.get("platforms", []) or []:
        if isinstance(platform, dict) and platform.get("name"):
            if platform["name"] not in names:
                names.append(platform["name"])

    # Some platforms may only appear in release_dates: add them at the end.
    for name in earliest_date:
        if name not in names:
            names.append(name)

    # Step 3: split the platforms in two groups.
    # - dated: platforms that have a release date.
    # - undated: platforms without any date, kept in their original order.
    # For the dated ones we remember their original position, so that two
    # platforms sharing the same date stay in their original order.
    dated = []
    undated = []
    for position, name in enumerate(names):
        date = earliest_date.get(name)
        if date is None:
            undated.append(name)
        else:
            dated.append((date, position, name))

    # Sorting the tuples compares the date first, then the original position.
    dated.sort()

    # Dated platforms first (earliest first), undated platforms last.
    ordered_names = [name for (date, position, name) in dated] + undated

    return ", ".join(ordered_names)


def _pick_display_name(game):
    """
        Choose the title to display for a game, preferring a French/European
        title over IGDB's default name (usually English):
          1. A French alternative title (alternative_names whose comment mentions
             France/French).
          2. The European localized title (game_localizations.name for the Europe
             region, id 4 — the same region find_poster prefers for covers).
          3. The game's default name.

        Requires game_localizations.name, game_localizations.region,
        alternative_names.name and alternative_names.comment in the queried
        fields. Shared by search_games (wizard list) and get_game (persisted
        title) so both show the same name.
    """

    # 1. French alternative title.
    for alt in game.get("alternative_names", []) or []:
        name = alt.get("name")
        comment = (alt.get("comment") or "").lower()
        if name and ("french" in comment or "france" in comment or "français" in comment or "francais" in comment):
            return name

    # 2. European localized title (Europe has id 4 in IGDB).
    for loc in game.get("game_localizations", []) or []:
        name = loc.get("name")
        region = loc.get("region")
        if name and isinstance(region, dict) and region.get("id") == 4:
            return name

    # 3. Default name.
    return game.get("name")


def search_games(query, page=1):

    """
        Search games on IGDB, return a list of VideoGame objects
    """

    offset = (page - 1) * IGDB_PAGE_SIZE
    body = 'fields name,cover.url,first_release_date,involved_companies.company.name,involved_companies.developer,involved_companies.publisher,platforms.name,release_dates.date,release_dates.platform.name,alternative_names.name,alternative_names.comment,game_localizations.cover.url,game_localizations.name,game_localizations.region.name; where name ~ *"%s"* ; sort first_release_date asc ; limit %d; offset %d ;' % (query.replace('"', '\\"'), IGDB_PAGE_SIZE, offset)

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

        # Extract platforms, ordered by ascending release date
        platforms = _platforms_by_release(game)

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

        # Build cover URL for display (same selection logic as get_game)
        poster_path = find_poster(game)

        game_obj = VideoGame(
            name=_pick_display_name(game),
            release_date=release_date,
            director=developer,
            external_id=game.get("id"),
            external_source="igdb",
            platforms=platforms,
            poster_path=poster_path
        )

        games_list.append(game_obj)

    return games_list


def get_game(external_id):
    """
        Get full game details from IGDB
    """

    body = 'fields name,summary,cover.url,first_release_date,involved_companies.company.name,involved_companies.developer,involved_companies.publisher,platforms.name,url,alternative_names.name,alternative_names.comment,release_dates.date,release_dates.region,release_dates.release_region.region,release_dates.platform.name,game_localizations.cover.url,game_localizations.name,game_localizations.region.name,game_localizations.region.identifier; where id = %s;' % str(external_id)

    results = _igdb_request("games", body)
    if not results or len(results) == 0:
        app.logger.error("Pas de réponse de l'API IGDB pour l'id %s", external_id)
        return None, []

    game = results[0]

    # Get the first release date and add additionnal details related to this first release date (Country and Platforms)
    first_ts = game.get("first_release_date")
    release_date = None
    if first_ts:
        try:
            release_date = datetime.utcfromtimestamp(first_ts).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass

    # Let's fetch the region by higher enabled priorities (Value >0)
    regions_list = Region.query.filter(Region.priority != 0).order_by(Region.priority.desc()).all()
    regions_by_id = {r.id: r for r in regions_list}
    region_release_dates = []

    # The objective is for each different release date, we check if it is for a region we want to import
    # If yes, we collect all the platforms for which the game has been released on that date for this region
    release_platform_by_date = {}
    for rd in game.get("release_dates", []) or []:
        cur_release_date = rd.get("date")
        if cur_release_date not in release_platform_by_date:
            release_platform_by_date[cur_release_date] = {}

        for cur_region in regions_list:
            
            # Fill the platform list for the current release date
            if rd.get("release_region").get("id") == cur_region.id:
                if cur_region.id not in release_platform_by_date[cur_release_date]:
                    release_platform_by_date[cur_release_date][cur_region.id] = []
                release_platform_by_date[cur_release_date][cur_region.id].append(rd.get("platform").get("name"))

    # VideoGameReleaseDate objet creation
    # region_release_date contains tuple with region/release_date/list of platforms for that release date
    for cur_rd in release_platform_by_date:

        # Convert the release date into the good format
        try:
            rd_date = datetime.utcfromtimestamp(cur_rd).date()
        except (ValueError, OSError, TypeError):
            rd_date = None

        for cur_region in release_platform_by_date[cur_rd]:
            release_platform_string = (',').join(release_platform_by_date[cur_rd][cur_region])
       
            region_release_dates.append(VideoGameReleaseDate(
                                        region_id=cur_region,
                                        region=regions_by_id.get(cur_region),
                                        release_date=rd_date,
                                        release_platform=release_platform_string)
            )
                                          
    # Fill the platform list, ordered by ascending release date
    platforms = _platforms_by_release(game)

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

    # Pick the cover (European localized if available, else the main one) and
    # download it. Same selection logic as the search results via find_poster,
    # but download the higher-resolution 2x variant since this poster is the one
    # shown on the confirm step and the display page (the wizard keeps t_cover_big).
    cover_url = find_poster(game)

    poster_path = None
    if cover_url:
        cover_url = cover_url.replace("t_cover_big", "t_cover_big_2x")
        if download_poster(cover_url):
            poster_path = os.path.basename(cover_url)

    # Pick the display title: European localized title, else a French alternative
    # title, else the original name (same logic as the wizard via search_games).
    original_name = game.get("name")
    display_name = _pick_display_name(game)

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
        external_source="igdb",
        poster_path=poster_path,
        director=developer,
        overview=translated_overview,
        overview_translated=overview_translated,
        platforms=platforms,
        publisher=publisher,
    )

    # Return the VideoGame objet and region_release_dates list seprately
    # The preparation for insertion or update in database is done on the add/update code from shows.py
    return game_obj, region_release_dates

def download_poster(url):
    """
        Download a cover image from IGDB
    """
    try:
        resp = requests.get(url)
        if resp.status_code != 200:
            return False

        # Validate the real image content before storing it — posters are served
        # from the public /static/posters — instead of trusting the response.
        if not is_allowed_image(BytesIO(resp.content)):
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
        Return how many result pages a query yields. Counts with the same
        `where name ~ "..."` clause as search_games, so the page count and the
        displayed results always agree.
    """
    import math
    body = 'where name ~ *"%s"*;' % query.replace('"', '\\"')

    result = _igdb_request("games/count", body)
    if result is None or "count" not in result:
        return 1

    total = result["count"]
    if total == 0:
        return 1

    return math.ceil(total / IGDB_PAGE_SIZE)
