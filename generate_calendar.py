#!/usr/bin/env python3
"""Build the Philippines cinema-releases calendar (.ics) from sources/cinema.json.

Behaviour (per the project plan / md):
  - Title is clean: "🍿 <Movie Title>"
  - Notes: synopsis, Director, Cast, Runtime, Status (PH confirmed / Expected PH),
    and a Date note only when there is a conflict or a placeholder date.
  - All-day, date-only events (timezone-proof for Asia/Manila).
  - Stable UIDs so Apple Calendar updates events in place instead of duplicating.
  - No VALARM blocks (the calendar sets no reminders).
  - Power Plant homepage in the URL field; no visible Links section.
  - 365-day look-ahead window.
  - Excludes films that have already opened ("Now Showing"): any date < today.
  - Empty-guard: refuses to write a (near-)empty calendar, so a bad run can't
    overwrite a good published file.

Data source (v1): the hand-maintained sources/cinema.json. A TMDB auto-fetch
layer can be added later and merged in BEFORE overrides are applied, with
sources/cinema.json always winning on conflicts.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from icalendar import Calendar, Event

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "sources" / "cinema.json"
OUT_DIR = ROOT / "public"
OUT_FILE = OUT_DIR / "calendar.ics"

POPCORN = "\U0001F37F"  # 🍿
PRODID = "-//ph-movie-calendar//cinema//EN"
CALNAME = "PH Cinema Releases"
CALDESC = "Upcoming cinema releases relevant to the Philippines."
POWERPLANT_URL = "https://powerplantcinema.com/bin/homepage.php"
WINDOW_DAYS = 365
MIN_EVENTS = 1  # empty-guard threshold

PLACEHOLDER_NOTE = "Global date used as placeholder until a PH cinema date is confirmed."
STATUS_LABEL = {"confirmed": "PH confirmed", "expected": "Expected PH"}


def build_description(m: dict) -> str:
    lines = [
        m["synopsis"].strip(),
        "",
        "Director:",
        m.get("director") or "TBC",
        "",
        "Cast:",
        m.get("cast") or "TBC",
        "",
        "Runtime:",
        m.get("runtime") or "Not listed yet",
        "",
        "Status:",
        STATUS_LABEL.get(m["status"], "Expected PH"),
    ]
    note = m.get("date_note")
    if not note and m["status"] == "expected":
        note = PLACEHOLDER_NOTE
    if note:
        lines += ["", "Date note:", note]
    return "\n".join(lines)


def load_movies() -> list[dict]:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{SOURCE} must contain a JSON list")
    return data


def in_window(d: date, today: date) -> bool:
    # Keep today and anything up to the look-ahead horizon; drop films that
    # have already opened (now showing) and anything beyond the window.
    return today <= d <= today + timedelta(days=WINDOW_DAYS)


def main() -> int:
    today = datetime.now(timezone.utc).date()
    stamp = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

    movies = load_movies()
    seen_uids: set[str] = set()
    kept: list[dict] = []
    for m in movies:
        try:
            d = date.fromisoformat(m["date"])
        except (KeyError, ValueError):
            print(f"  skip (bad/missing date): {m.get('title', m)}", file=sys.stderr)
            continue
        if not in_window(d, today):
            continue
        uid = m["uid"]
        if uid in seen_uids:  # de-dup
            continue
        seen_uids.add(uid)
        m["_date"] = d
        kept.append(m)

    kept.sort(key=lambda x: x["_date"])

    if len(kept) < MIN_EVENTS:
        print(f"ERROR: only {len(kept)} events in window — refusing to publish.",
              file=sys.stderr)
        return 1

    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", CALNAME)
    cal.add("x-wr-caldesc", CALDESC)
    cal.add("x-wr-timezone", "Asia/Manila")
    cal.add("x-published-ttl", "PT12H")
    cal.add("refresh-interval;value=duration", "PT12H")

    for m in kept:
        ev = Event()
        ev.add("uid", f"{m['uid']}@ph-movie-calendar")
        ev.add("dtstamp", stamp)
        ev.add("summary", f"{POPCORN} {m['title']}")
        ev.add("dtstart", m["_date"])  # date object -> all-day VALUE=DATE
        ev.add("dtend", m["_date"] + timedelta(days=1))
        ev.add("transp", "TRANSPARENT")
        ev.add("description", build_description(m))
        ev.add("url", POWERPLANT_URL)
        cal.add_component(ev)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_bytes(cal.to_ical())
    print(f"Wrote {OUT_FILE} with {len(kept)} events (window {WINDOW_DAYS}d from {today}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
