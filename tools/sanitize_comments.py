#!/usr/bin/env python
"""
Re-sanitize every stored rating comment (Mark.comment) against the current
server-side allow-list (cineapp.utils.sanitize_comment / nh3).

Why this tool exists
--------------------
Mark.comment is the only comment field stored as raw HTML and rendered
*unescaped* — with `|safe` in display_show.html and injected as-is into the
list-page bubble / activity feed. New comments are sanitized on write
(shows.py calls sanitize_comment()), but rows written *before* that guard was
added — or written by a non-browser HTTP client that bypassed CKEditor — may
still hold unsanitized markup. This is the stored-XSS (CWE-79) surface from the
security audit. Running this tool brings the whole existing corpus up to the
same allow-list the write path enforces.

What it does NOT touch — and why
--------------------------------
MarkComment.message (the sub-comments under a review) is rendered *escaped*
everywhere ({{ cur_comment.message }} in display_show.html, escapeHtml() in the
JS, {{ ... }} in the activity feed), so it is not an injection vector. It is
also free-form plain text, so running nh3.clean() on it would silently corrupt
legitimate content (e.g. "5 < 6" would lose "< 6"). It is therefore left
untouched on purpose.

Idempotent: sanitize_comment() is stable, so re-running this tool over an
already-clean corpus reports zero changes. Each change is committed on its own,
so a failure on one row neither aborts the run nor rolls back earlier work.

This is a standalone CLI tool: it builds the application context with
create_app() / app_context(). There is NO web server and NO login involved.

Usage:
    python tools/sanitize_comments.py --config configs/settings.cfg --dry-run
    python tools/sanitize_comments.py --config configs/settings.cfg
    python tools/sanitize_comments.py --config configs/settings.cfg --limit 100
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cineapp import create_app
from cineapp.models import db, Mark
from cineapp.utils import sanitize_comment


def collect_targets():
    """Return every Mark row that actually carries a comment, ordered stably."""
    return (Mark.query
            .filter(Mark.comment != None)       # noqa: E711 — SQL IS NOT NULL
            .filter(Mark.comment != "")
            .order_by(Mark.user_id, Mark.show_id)
            .all())


def main():
    parser = argparse.ArgumentParser(
        description="Re-sanitize all stored rating comments (Mark.comment) "
                    "against the current sanitize_comment() allow-list")
    parser.add_argument("--config", required=True,
                        help="Path to cineapp config file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without writing anything")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after scanning N comments (0 = all)")
    parser.add_argument("--show-diff", action="store_true",
                        help="Print the before/after markup for each changed row")
    args = parser.parse_args()

    app = create_app(args.config)

    with app.app_context():
        targets = collect_targets()
        if not targets:
            print("No stored comment found.")
            return

        total = len(targets) if args.limit == 0 else min(args.limit, len(targets))
        mode = "DRY-RUN — no write" if args.dry_run else "WRITING changes"
        print("Scanning %d comment(s) [%s]..." % (total, mode))

        changed = unchanged = failed = 0
        for idx, mark in enumerate(targets[:total], 1):
            original = mark.comment
            try:
                cleaned = sanitize_comment(original)
            except Exception as exc:  # noqa: BLE001 — keep going on isolated failures
                failed += 1
                print("[%5d/%d] KO   user=%s show=%s  (sanitize error: %s)"
                      % (idx, total, mark.user_id, mark.show_id, exc))
                continue

            if cleaned == original:
                unchanged += 1
                continue

            changed += 1
            print("[%5d/%d] %s  user=%s show=%s  (%d -> %d chars)"
                  % (idx, total,
                     "WOULD CLEAN" if args.dry_run else "CLEANED",
                     mark.user_id, mark.show_id, len(original), len(cleaned)))
            if args.show_diff:
                print("    - before: %r" % original)
                print("    - after : %r" % cleaned)

            if not args.dry_run:
                mark.comment = cleaned
                try:
                    db.session.add(mark)
                    db.session.commit()
                except Exception as exc:  # noqa: BLE001
                    db.session.rollback()
                    changed -= 1
                    failed += 1
                    print("           KO  commit failed: %s" % exc)

    verb = "would be cleaned" if args.dry_run else "cleaned"
    print("Done. %d %s, %d already clean, %d failed (out of %d)."
          % (changed, verb, unchanged, failed, total))


if __name__ == "__main__":
    main()
