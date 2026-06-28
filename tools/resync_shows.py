#!/usr/bin/env python
"""
Resync every movie and TV show stored in the database directly against the
TheMovieDB API — metadata AND poster.

This is a standalone CLI tool: it builds the application context with
create_app() / app_context() and talks to TMDB through the existing
cineapp.tmvdb helpers. There is NO web server and NO login involved.

For each show, get_show(external_id, fetch_poster=True, show_type=...) is
called. That helper refreshes the metadata and re-downloads the poster into
POSTERS_PATH (returning a fresh, transient object). The refreshed fields are
then copied onto the persisted row and committed one show at a time, so a
failure on a single show neither aborts the run nor rolls back earlier work.

Only shows with external_source='tmvdb' and a non-null external_id are
processed (others have no TMDB id to look up).

Open design decisions (prudent defaults applied — flip if you disagree):
  (a) Missing poster on resync: keep the existing artwork rather than wiping
      it to None on a transient API miss (see resync_show()).
  (b) File name: kept as resync_shows.py (it resyncs movies AND TV shows, so
      the older tvshow-only name no longer fits).

Usage:
    python tools/resync_shows.py --config configs/settings.cfg
    python tools/resync_shows.py --config configs/settings.cfg --only movie
    python tools/resync_shows.py --config configs/settings.cfg --sleep 1 --limit 50
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import current_app

from cineapp import create_app
from cineapp.models import db, Movie, TVShow
from cineapp.tmvdb import get_show


# show_type -> model. The keys match cineapp.tmvdb.tmvdb_mode / g.show_type.
SHOW_MODELS = {"movie": Movie, "tvshow": TVShow}


def resync_show(show, show_type):
    """Refresh one persisted show in place from TMDB.

    Fetches a fresh transient object via get_show (which also re-downloads the
    poster into POSTERS_PATH), copies the refreshed fields onto the existing
    row and commits. Returns (ok, detail).
    """
    temp_show = get_show(show.external_id, fetch_poster=True, show_type=show_type)

    if temp_show is None:
        return False, "no API response for external_id=%s" % show.external_id

    # Copy the fields TMDB owns. type/origin are user-curated (set via the web
    # wizard, not by TMDB) so they are intentionally left untouched.
    old_poster = show.poster_path
    show.name = temp_show.name
    show.original_name = temp_show.original_name
    show.release_date = temp_show.release_date
    show.url = temp_show.url
    show.director = temp_show.director
    show.overview = temp_show.overview

    # Decision (a) — prudent default: keep the current poster if TMDB returned
    # none this time, rather than wiping a working artwork on a transient API
    # hiccup. (Flip to `show.poster_path = temp_show.poster_path` to mirror the
    # raw API state instead.)
    if temp_show.poster_path:
        show.poster_path = temp_show.poster_path
        # A new poster was downloaded into POSTERS_PATH by get_show(). If its
        # file name differs from the previous one, the old file is now an
        # orphan on disk — delete it (same pattern as the avatar swap in
        # profile.py). When the file name is unchanged, download_poster already
        # overwrote it in place, so there is nothing to remove. Best-effort:
        # a failed cleanup must not fail the resync.
        if old_poster and old_poster != temp_show.poster_path:
            try:
                os.remove(os.path.join(current_app.config['POSTERS_PATH'], old_poster))
                poster_detail = "poster refreshed (old removed)"
            except OSError:
                poster_detail = "poster refreshed (old removal failed)"
        else:
            poster_detail = "poster refreshed"
    else:
        poster_detail = "poster kept (none returned)"

    if isinstance(show, Movie):
        show.duration = temp_show.duration
    elif isinstance(show, TVShow):
        show.nb_seasons = temp_show.nb_seasons
        show.production_status = temp_show.production_status

    db.session.add(show)
    db.session.commit()
    return True, poster_detail


def collect_targets(only):
    """Return [(show_type, id, name), ...] for every TMDB-sourced show."""
    targets = []
    for show_type, model in SHOW_MODELS.items():
        if only and only != show_type:
            continue
        rows = (model.query
                .filter(model.external_source == 'tmvdb')
                .filter(model.external_id != None)
                .order_by(model.id)
                .all())
        targets.extend((show_type, r.id, r.name) for r in rows)
    return targets


def main():
    parser = argparse.ArgumentParser(
        description="Resync all movies and TV shows (metadata + posters) from TheMovieDB")
    parser.add_argument("--config", required=True, help="Path to cineapp config file")
    parser.add_argument("--only", choices=["movie", "tvshow"], default=None,
                        help="Restrict the resync to a single show type (default: both)")
    parser.add_argument("--sleep", type=float, default=0.5,
                        help="Delay in seconds between two shows (TMDB rate-limit hygiene)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after N shows (0 = all)")
    args = parser.parse_args()

    app = create_app(args.config)

    with app.app_context():
        targets = collect_targets(args.only)

        if not targets:
            print("No movie or TV show with a TMDB external_id found.")
            return

        total = len(targets) if args.limit == 0 else min(args.limit, len(targets))
        print("Resyncing %d show(s) from TheMovieDB..." % total)

        ok = ko = 0
        for idx, (show_type, sid, name) in enumerate(targets[:total], 1):
            try:
                show = SHOW_MODELS[show_type].query.get(sid)
                success, detail = resync_show(show, show_type)
            except Exception as exc:  # noqa: BLE001 — keep going on isolated failures
                db.session.rollback()
                success, detail = False, "exception: %s" % exc

            tag = "OK" if success else "KO"
            print("[%4d/%d] %s  %-7s #%d  %s  (%s)"
                  % (idx, total, tag, show_type, sid, name, detail))
            if success:
                ok += 1
            else:
                ko += 1

            if args.sleep > 0 and idx < total:
                time.sleep(args.sleep)

    print("Done. %d ok, %d failed (out of %d)." % (ok, ko, total))


if __name__ == "__main__":
    main()
