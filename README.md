# PH Cinema Releases — auto-updating calendar

A subscribe-once Apple Calendar of upcoming cinema releases relevant to the
Philippines. A daily GitHub job fetches the latest releases live, rebuilds the
calendar, and publishes it; your phone refreshes the subscription on its own.
Your Mac doesn't need to be on, and there is **no hand-maintained film list** —
the content comes straight from the cinema sources every run.

## How it works

```
PH cinema sources   ->   generate_calendar.py   ->   public/calendar.ics
   (ClickTheCity)          (fetch + build)             (what you subscribe to)
                                  |
                       GitHub Actions runs it daily
                                  |
                         GitHub Pages serves it
                                  |
                       Apple Calendar refreshes it
```

* **`generate_calendar.py`** drives a headless browser (Playwright/Chromium) to
  read the Philippine release data live — title, synopsis, director, cast, PH
  release date, runtime — and builds `public/calendar.ics` from it. Nothing is
  hard-coded; if a film isn't listed at the source, it isn't in the calendar.
* **`.github/workflows/update-calendar.yml`** runs the builder every day at
  02:00 Manila time and publishes the result to GitHub Pages. You can also
  trigger it by hand from the repo's **Actions** tab.

The build follows the project plan: clean `🍿 Title` events; a short synopsis
with Director / Cast / Runtime / Status; all-day, timezone-proof dates; stable
per-film IDs so events update in place instead of duplicating; the Power Plant
homepage in the calendar's link field; no built-in reminders; a 365-day
look-ahead; and films that have already opened drop off automatically. If a run
somehow scrapes nothing, it refuses to publish so it can't overwrite a good
calendar with an empty one.

## Subscribe

```
https://2bkj9stccf-gif.github.io/ph-movie-calandar/calendar.ics
```

* **iPhone:** Settings → Calendar → Accounts → Add Account → Other →
  Add Subscribed Calendar → paste the URL.
* **Mac (Calendar app):** File → New Calendar Subscription → paste the URL.

Tip: give it its own colour, and to avoid surprise pop-ups turn off default
all-day alerts: Settings → Apps → Calendar → Default Alert Times →
All-Day Events → None.

## Data sources

Currently the live source is **ClickTheCity** (Philippine release dates and
details). Planned additions: **Power Plant Cinema** as a higher-priority date
override, plus SM / Ayala-SureSeats / Vista and IMDb's PH calendar, and an
"Expected PH" layer that surfaces major global releases (using the global date
as a placeholder) before they're locally dated.
