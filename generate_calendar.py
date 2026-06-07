#!/usr/bin/env python3
"""Build the Philippines cinema-releases calendar (.ics) — LIVE SOURCED.

Data is fetched fresh every run from the PH cinema sources in the project md
(currently ClickTheCity; Power Plant + others layer in as date-priority
overrides). There is NO hand-maintained film list.

ClickTheCity renders its data with JavaScript, so we drive a headless Chromium
(Playwright) to render each page and read the structured JSON-LD "Movie" block,
which carries title, synopsis, director, cast, the PH release date, runtime and
rating — i.e. everything the md's notes format needs.

Output: public/calendar.ics (md-compliant: clean 🍿 titles; Status on every
event; all-day date-only; stable UIDs; Power Plant URL field; no VALARM;
365-day window; excludes films already opened). Empty-guard: a run that
scrapes nothing exits non-zero so a bad run can't overwrite the live file.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from icalendar import Calendar, Event
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "public"
OUT_FILE = OUT_DIR / "calendar.ics"

POPCORN = "\U0001F37F"
PRODID = "-//ph-movie-calendar//cinema//EN"
CALNAME = "PH Cinema Releases"
CALDESC = "Upcoming cinema releases relevant to the Philippines."
POWERPLANT_URL = "https://powerplantcinema.com/bin/homepage.php"
WINDOW_DAYS = 365
MIN_EVENTS = 1
MAX_CAST = 5

CTC = "https://www.clickthecity.com"
CTC_COMING_SOON = f"{CTC}/movies/coming-soon"

STATUS_LABEL = {"confirmed": "PH confirmed", "expected": "Expected PH"}
PLACEHOLDER_NOTE = "Global date used as placeholder until a PH cinema date is confirmed."


# ---------------------------------------------------------------- scraping ---
def _collect_detail_urls(page) -> list[str]:
    """Render the Coming Soon listing and collect unique movie detail URLs."""
    # Ad scripts keep the network busy, so never wait for "networkidle" — wait
    # for the actual movie links to render instead.
    page.goto(CTC_COMING_SOON, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector('a[href*="/movies/title/"]', timeout=30000)
    except Exception:
        pass
    # lazy content: scroll to the bottom a few times
    for _ in range(6):
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(700)
    hrefs = page.eval_on_selector_all(
        'a[href*="/movies/title/"]',
        "els => els.map(e => e.getAttribute('href'))",
    )
    seen, urls = set(), []
    for h in hrefs:
        if not h or "/movies/title/" not in h:
            continue
        path = h if h.startswith("http") else CTC + h
        path = path.split("?")[0].rstrip("/")
        if path not in seen:
            seen.add(path)
            urls.append(path)
    return urls


def _ldjson_movie(page) -> dict | None:
    """Return the JSON-LD object with @type == 'Movie' on the current page."""
    blobs = page.eval_on_selector_all(
        'script[type="application/ld+json"]',
        "els => els.map(e => e.textContent)",
    )
    for raw in blobs:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if isinstance(obj, dict) and obj.get("@type") == "Movie":
                return obj
    return None


def _ctc_id(url: str) -> str:
    m = re.search(r"/movies/title/([^/]+)/", url + "/")
    return m.group(1) if m else re.sub(r"\W+", "-", url)[-12:]


def _parse_runtime(duration: str | None) -> str | None:
    """ClickTheCity reports e.g. 'PT1 hr 41 minM' or 'PT2 hours'. Pull the
    hours and minutes out robustly and render '1h 41m'."""
    if not duration:
        return None
    h = re.search(r"(\d+)\s*h", duration)        # '1 hr', '2 hours', '1h'
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


def _names(value) -> list[str]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    out = []
    for it in items:
        if isinstance(it, dict) and it.get("name"):
            out.append(it["name"])
        elif isinstance(it, str):
            out.append(it)
    return out


def scrape_clickthecity() -> list[dict]:
    movies: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ))
        try:
            urls = _collect_detail_urls(page)
            print(f"ClickTheCity: {len(urls)} coming-soon titles")
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    # The Movie JSON-LD is injected after hydration; poll for it.
                    obj = None
                    for _ in range(5):
                        obj = _ldjson_movie(page)
                        if obj:
                            break
                        page.wait_for_timeout(1500)
                    if not obj:
                        print(f"  no Movie data: {url}", file=sys.stderr)
                        continue
                    pub = obj.get("datePublished")
                    if not pub:
                        continue
                    try:
                        d = date.fromisoformat(pub[:10])
                    except ValueError:
                        continue
                    cast = _names(obj.get("actor"))[:MAX_CAST]
                    movies.append({
                        "uid": f"ctc-{_ctc_id(url)}",
                        "title": (obj.get("name") or "").strip(),
                        "date": d,
                        "status": "confirmed",
                        "synopsis": _clean_synopsis(obj.get("description")),
                        "director": ", ".join(_names(obj.get("director"))) or "TBC",
                        "cast": ", ".join(cast) or "TBC",
                        "runtime": _parse_runtime(obj.get("duration")),
                        "date_note": None,
                    })
                except Exception as e:  # one bad page must not sink the run
                    print(f"  error {url}: {e}", file=sys.stderr)
        finally:
            browser.close()
    return movies


# -------------------------------------------------------------- build .ics ---
def build_description(m: dict) -> str:
    lines = [
        (m["synopsis"] or "").strip(),
        "", "Director:", m.get("director") or "TBC",
        "", "Cast:", m.get("cast") or "TBC",
        "", "Runtime:", m.get("runtime") or "Not listed yet",
        "", "Status:", STATUS_LABEL.get(m["status"], "Expected PH"),
    ]
    note = m.get("date_note") or (PLACEHOLDER_NOTE if m["status"] == "expected" else None)
    if note:
        lines += ["", "Date note:", note]
    return "\n".join(lines)


def main() -> int:
    today = datetime.now(timezone.utc).date()
    stamp = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

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
        print(f"ERROR: scraped {len(kept)} usable events — refusing to publish.",
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
        ev.add("dtstart", m["date"])
        ev.add("dtend", m["date"] + timedelta(days=1))
        ev.add("transp", "TRANSPARENT")
        ev.add("description", build_description(m))
        ev.add("url", POWERPLANT_URL)
        cal.add_component(ev)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_bytes(cal.to_ical())
    print(f"Wrote {OUT_FILE}: {len(kept)} events (live from ClickTheCity, {today}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
