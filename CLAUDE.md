# SwiftQueue Checker

A Flask web app that monitors SwiftQueue for appointment slots earlier than each user's target date. Sends Telegram alerts and shows available slots live on the page.

## What it does

- Users register via web UI: pick an area, set a target date
- On first registration for an area, immediately scrapes SwiftQueue for available slots
- Checker polls all watched URLs every 60s (staggered, one per second)
- Available slots matching a user's criteria shown on the page, auto-refreshed (synced to scrape cycle)
- Toast notification on page when a new slot appears
- Telegram alerts sent when new slots are found; message edited when slot disappears
- Multiple Telegram accounts can be linked per subscription via a shareable link
- On unsubscribe, farewell Telegram message sent to all linked accounts
- Slot state persisted in SQLite; restarts don't cause duplicate alerts

## Architecture

Two Docker services sharing a SQLite database (`data/swiftqueue.db`) via a named volume:

- **web** — Flask app (gunicorn in prod, dev server locally), handles registration/unsubscribe UI and slot/status API
- **checker** — background poller, diffs slots against DB state, dispatches Telegram notifications and account-linking

## Key files

- `app/__init__.py` — Flask app factory
- `app/db.py` — SQLite schema, `get_db()` context manager, `init_db()`
- `app/areas.py` — curated dict of `{name: url}` for the area dropdown
- `app/scraper.py` — `fetch_slots(url)` HTML parser (if SwiftQueue changes structure, check here)
- `app/notifications.py` — `send_telegram()` and `edit_telegram_message()` via Bot API
- `app/routes.py` — Flask routes: `/`, `/register`, `/slots/<token>`, `/registration/<token>`, `/unsubscribe/<token>`, `/status`
- `checker/worker.py` — polling loop, slot diffing, Telegram notifications, account-linking listener
- `static/sw.js` — minimal service worker (notificationclick only)
- `static/app.js` — registration form, slot polling, toast notifications, Telegram UI
- `templates/index.html` — registration/status page
- `templates/unsubscribe.html` — unsubscribe confirmation

## DB schema

- `users` — token, area_url, target_date, active
- `active_slots` — url, slot_date, slot_time, clinic (currently available slots per URL)
- `area_meta` — url, last_scraped_at (used by frontend to sync poll timing to scrape cycle)
- `telegram_subscribers` — token, chat_id, UNIQUE(token, chat_id) — multiple accounts per subscription
- `telegram_messages` — token, chat_id, message_id, slot details (for editing messages when slot disappears)

## Setup

```bash
cp .env.example .env
# fill in .env (see below)
```

Run locally:
```bash
pip install -r requirements.txt
flask --app "app:create_app()" run       # web
python -m checker.worker                  # checker (separate terminal)
```

Or with Docker:
```bash
docker compose up
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask session secret |
| `TELEGRAM_TOKEN` | No | Bot token — enables Telegram alerts |
| `TELEGRAM_BOT_USERNAME` | No | e.g. `MySwiftQueueBot` — shows Telegram link button in UI |

## Notes

- `data/` is gitignored and created at runtime; mount it as a Docker volume
- `app/areas.py` is the only place to add new SwiftQueue locations
- On first registration for a URL, the web process immediately scrapes SwiftQueue and seeds `active_slots` — no 60s wait
- Frontend polls `/slots/<token>` on a dynamic schedule: 5s after each expected scrape, based on `area_meta.last_scraped_at`
- SQLite WAL mode is enabled so both services can read/write concurrently without locking
- Telegram linking is per-token; multiple chat_ids can link via a shareable `/start <token>` link
- Re-subscribing after unsubscribing creates a new token — Telegram must be re-linked
