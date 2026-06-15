#!/usr/bin/env python3
"""Build the Philippines cinema-releases calendar (.ics) — LIVE SOURCED.

Data comes fresh every run from ClickTheCity's JSON API
(`/api/movies/upcoming`), which returns the upcoming PH cinema releases with
title, synopsis, director, cast, genre, runtime and the PH release date. There
is NO hand-maintained film list.

We deliberately hit the API rather than scraping the rendered Coming Soon page:
that page is a client-side app that periodically throws "Something went wrong"
and renders no movie links (which silently produced an empty calendar). The API
behind it stays healthy, needs no login, and gives clean structured data — so
it's both simpler and far more robust. No headless browser required.

The API returns the nearest ~10 upcoming films per call (pagination is not
exposed), so retention does double duty: it carries forward previously-published
events (both recent past AND still-future films not in the latest API page) so
the calendar keeps its full rolling slate instead of collapsing to 10 entries.

Output: public/calendar.ics (md-compliant: clean 🎬 titles; Status on every
event; all-day date-only; stable UIDs; Power Plant URL field; no VALARM).
Empty-guard: a run that fetches nothing exits non-zero so a bad run can't
overwrite the live file.
"""
from __future__ import annotations

import calendar as _calmod
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from icalendar import Calendar, Event

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "public"
OUT_FILE = OUT_DIR / "calendar.ics"

ICON = "\U0001F3AC"  # 🎬 clapper (movie calendar)
PRODID = "-//ph-movie-calendar//cinema//EN"
CALNAME = "PH Cinema Releases"
CALDESC = "Upcoming cinema releases relevant to the Philippines."
POWERPLANT_URL = "https://powerplantcinema.com/bin/homepage.php"
# The currently-published calendar. Retention reads THIS (not the committed
# repo copy) so films accumulate across daily Pages deploys — the workflow
# never commits calendar.ics back, so the repo copy is a frozen seed.
PUBLISHED_URL = "https://2bkj9stccf-gif.github.io/ph-movie-calandar/calendar.ics"
# ClickTheCity upcoming-movies JSON API (the data source behind Coming Soon).
API_URL = "https://www.clickthecity.com/api/movies/upcoming"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
WINDOW_DAYS = 365
RETENTION_MONTHS = 6  # keep already-opened films this many months after release
MIN_EVENTS = 1
MAX_CAST = 5

STATUS_LABEL = {"confirmed": "PH confirmed", "expected": "Expected PH"}
PLACEHOLDER_NOTE = "Global date used as placeholder until a PH cinema date is confirmed."


# ----------------------------------------------------------------- helpers ---
def _parse_runtime(duration: str | None) -> str | None:
    """ClickTheCity reports e.g. '2 hrs 42 min' or '1 hr 35 min'. Pull the
    hours and minutes out robustly and render '2h 42m'."""
    if not duration:
        return None
    h = re.search(r"(\d+)\s*h", duration)        # '1 hr', '2 hrs', '1h'
    m = re.search(r"(\d+)\s*m(?:in)?", duration)  # '41 min', '41m'
    parts = []
    if h:
        parts.append(f"{int(h.group(1))}h")
    if m:
        parts.append(f"{int(m.group(1))}m")
    return " ".join(parts) or None


def _clean_synopsis(text: str | None, limit: int = 280) -> str:
    """Collapse whitespace and trim to a clean, calendar-friendly length,
    preferring to end on a sentence boundary."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > limit * 0.5:
            return cut[: idx + 1].strip()
    return cut.rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def _api_names(items) -> list[str]:
    """Pull display names out of an API person list (director / main_cast)."""
    out = []
    for it in (items or []):
        if isinstance(it, dict) and it.get("name"):
            out.append(it["name"].strip())
        elif isinstance(it, str) and it.strip():
            out.append(it.strip())
    return out


# ------------------------------------------------------------------ fetch ---
def parse_api_movies(payload: dict) -> list[dict]:
    """Map ClickTheCity's /api/movies/upcoming JSON into our event dicts."""
    rows = payload.get("data") if isinstance(payload, dict) else None
    movies: list[dict] = []
    for m in (rows or []):
        title = (m.get("title") or "").strip()
        if not title:
            continue
        try:
            d = date.fromisoformat((m.get("release_date") or "")[:10])
        except ValueError:
            continue  # no usable PH release date
        # UID matches the historical scheme `ctc-<hash>` so events update in
        # place (the old scraper derived <hash> from the /movies/title/<hash>/
        # URL; the API hands us that same hash directly).
        uid = m.get("hash") or m.get("movie_id")
        cast = _api_names(m.get("main_cast"))[:MAX_CAST]
        movies.append({
            "uid": f"ctc-{uid}",
            "title": title,
            "date": d,
            "status": "confirmed",
            "synopsis": _clean_synopsis(m.get("synopsis")),
            "genre": (m.get("genre") or "").strip() or None,
            "director": ", ".join(_api_names(m.get("director"))) or "TBC",
            "cast": ", ".join(cast) or "TBC",
            "runtime": _parse_runtime(m.get("running_time")),
            "date_note": None,
        })
    return movies


def scrape_clickthecity() -> list[dict]:
    """Fetch upcoming PH releases from the ClickTheCity JSON API."""
    req = urllib.request.Request(
        API_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  ClickTheCity API fetch failed: {e}", file=sys.stderr)
        return []
    movies = parse_api_movies(payload)
    print(f"ClickTheCity API: {len(movies)} upcoming titles")
    return movies


# -------------------------------------------------------------- build .ics ---
def build_description(m: dict) -> str:
    lines = [(m["synopsis"] or "").strip()]
    # Genre and runtime show as bare values (no labels), each on its own line
    # with a blank line between; runtime only if known.
    for item in (m.get("genre"), m.get("runtime")):
        if item:
            lines += ["", item]
    lines += ["", "Director:", m.get("director") or "TBC"]
    lines += ["", "Cast:", m.get("cast") or "TBC"]
    lines += ["", "Status:", STATUS_LABEL.get(m["status"], "Expected PH")]
    note = m.get("date_note") or (PLACEHOLDER_NOTE if m["status"] == "expected" else None)
    if note:
        lines += ["", "Date note:", note]
    return "\n".join(lines)


def _months_ago(d: date, n: int) -> date:
    """Return the date n calendar months before d (clamped to month length)."""
    month = d.month - n
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    day = min(d.day, _calmod.monthrange(year, month)[1])
    return date(year, month, day)


def _event_date(ev) -> date | None:
    """Pull the date out of an existing VEVENT's DTSTART (date-only or datetime)."""
    dt = ev.get("dtstart")
    if dt is None:
        return None
    val = dt.dt
    return val.date() if isinstance(val, datetime) else val


def _load_previous_calendar() -> Calendar | None:
    """Load the previously published calendar to carry history forward.

    Prefer the LIVE published file (PUBLISHED_URL): the daily workflow deploys
    to GitHub Pages without committing calendar.ics back, so the repo copy is a
    frozen seed. Reading the live file is what lets the calendar accumulate run
    over run. Fall back to the local committed copy if the fetch fails."""
    try:
        req = urllib.request.Request(PUBLISHED_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            return Calendar.from_ical(r.read())
    except Exception as e:
        print(f"  could not fetch published calendar ({e}); trying local copy", file=sys.stderr)
    if OUT_FILE.exists():
        try:
            return Calendar.from_ical(OUT_FILE.read_bytes())
        except Exception as e:
            print(f"  could not read local calendar for retention: {e}", file=sys.stderr)
    return None


def load_retained_events(lo: date, hi: date, exclude_uids: set[str]):
    """Carry forward previously-published events dated in [lo, hi] that the
    fresh fetch didn't supply.

    This preserves BOTH recent past films (so already-opened titles linger for
    RETENTION_MONTHS) AND still-future films that the API's short
    nearest-10 window no longer lists — without this, the calendar would shrink
    to ~10 entries every run. Fresh-fetched UIDs are excluded so the latest data
    wins on anything still in the API window."""
    old = _load_previous_calendar()
    if old is None:
        return []
    retained = []
    for comp in old.walk("VEVENT"):
        d = _event_date(comp)
        if d is None:
            continue
        if not (lo <= d <= hi):
            continue
        uid = str(comp.get("uid") or "")
        if uid in exclude_uids:
            continue  # the fresh fetch has a newer copy
        retained.append(comp)
    return retained


def main() -> int:
    today = datetime.now(timezone.utc).date()
    stamp = datetime.now(timezone.utc)  # build time → reliably signals updates

    movies = scrape_clickthecity()

    seen, kept = set(), []
    for m in movies:
        d = m["date"]
        if not m["title"]:
            continue
        if not (today <= d <= today + timedelta(days=WINDOW_DAYS)):
            continue  # exclude already-opened + beyond-window
        if m["uid"] in seen:
            continue
        seen.add(m["uid"])
        kept.append(m)
    kept.sort(key=lambda x: x["date"])

    if len(kept) < MIN_EVENTS:
        print(f"ERROR: fetched {len(kept)} usable events — refusing to publish.",
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
        ev.add("last-modified", stamp)
        ev.add("summary", f"{ICON} {m['title']}")
        ev.add("dtstart", m["date"])
        ev.add("dtend", m["date"] + timedelta(days=1))
        ev.add("transp", "TRANSPARENT")
        ev.add("description", build_description(m))
        ev.add("url", POWERPLANT_URL)
        cal.add_component(ev)

    # Carry forward previously-published films the API's short window dropped:
    # recent past (rolling RETENTION_MONTHS) AND still-future titles, so the
    # calendar keeps its full slate instead of collapsing to the latest ~10.
    retain_start = _months_ago(today, RETENTION_MONTHS)
    window_end = today + timedelta(days=WINDOW_DAYS)
    new_uids = {f"{u}@ph-movie-calendar" for u in seen}
    retained = load_retained_events(retain_start, window_end, new_uids)
    for comp in retained:
        cal.add_component(comp)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_bytes(cal.to_ical())
    print(f"Wrote {OUT_FILE}: {len(kept)} fresh + {len(retained)} retained "
          f"events (kept {retain_start} .. {window_end}, from ClickTheCity API, {today}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
