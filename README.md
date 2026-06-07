# PH Cinema Releases — auto-updating calendar

A subscribe-once Apple Calendar of upcoming cinema releases relevant to the
Philippines. A daily GitHub job rebuilds the calendar and publishes it; your
phone refreshes the subscription on its own. Your Mac doesn't need to be on.

## How it works

```
sources/cinema.json   ->   generate_calendar.py   ->   public/calendar.ics
        (the films)            (the builder)              (what you subscribe to)
                                     |
                          GitHub Actions runs it daily
                                     |
                            GitHub Pages serves it
                                     |
                         Apple Calendar refreshes it
```

* **`sources/cinema.json`** — the list of films. This is the one file you edit
  to add, remove, or correct a movie.
* **`generate_calendar.py`** — turns that list into `public/calendar.ics`,
  applying the formatting and rules (clean titles, status line, date notes,
  365-day window, drops films once they've opened, refuses to publish an empty
  calendar).
* **`.github/workflows/update-calendar.yml`** — runs the builder every day at
  02:00 Manila time and publishes the result. You can also trigger it by hand
  from the repo's **Actions** tab.

## One-time setup

1. Create a new **public** GitHub repository named `ph-movie-calendar` and
   upload these files (keep the folder structure).
2. In the repo: **Settings → Pages → Build and deployment → Source: GitHub
   Actions**.
3. Open the **Actions** tab and run **Update calendar** once (or just push a
   change). When it finishes, your calendar lives at:

   ```
   https://YOUR-GITHUB-USERNAME.github.io/ph-movie-calendar/calendar.ics
   ```

## Subscribe on your devices

* **iPhone:** Settings → Calendar → Accounts → Add Account → Other →
  Add Subscribed Calendar → paste the URL above.
* **Mac (Calendar app):** File → New Calendar Subscription → paste the URL.

Tip: set the subscription's auto-refresh to a short interval, and to avoid
surprise pop-ups, turn off default all-day alerts:
Settings → Apps → Calendar → Default Alert Times → All-Day Events → None.

## Editing the film list

Each entry in `sources/cinema.json` looks like:

```json
{
  "uid": "toy-story-5",
  "title": "Toy Story 5",
  "date": "2026-06-17",
  "status": "confirmed",
  "synopsis": "Short non-spoiler synopsis.",
  "director": "Andrew Stanton",
  "cast": "Tom Hanks, Tim Allen",
  "runtime": null,
  "date_note": "Optional note, only shown if there is a conflict or placeholder."
}
```

* `status` is `"confirmed"` (a PH source has dated it) or `"expected"`
  (a major global release using its global date as a placeholder).
* `uid` must stay the same for a film forever — that's how the calendar updates
  an event in place instead of creating a duplicate. If a date changes, just
  change `date` and keep the `uid`.
* Leave `runtime` as `null` until a reliable runtime is known.
* `date_note` can be `null`. Expected-PH films automatically get the standard
  placeholder note even if you leave it `null`.

## Coming next

Step two will add an automatic TMDB fetch so new releases and dates flow in
without hand-editing. The TMDB layer will merge in *before* this file, and
`sources/cinema.json` will always win — so your manual fixes are never
overwritten.
