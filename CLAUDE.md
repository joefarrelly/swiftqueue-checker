# SwiftQueue Checker

A Flask web app that monitors SwiftQueue for appointment slots earlier than each user's target date. Sends Telegram alerts and shows available slots live on the page.

Live at [queue4me.uk](https://queue4me.uk).

## What it does

- Users register via web UI: pick an area, set a target date
- On first registration for an area, immediately scrapes SwiftQueue for available slots and seeds `area_meta`
- Checker polls all watched URLs every 60s (staggered, one per second)
- Available slots matching a user's criteria shown on the page, auto-refreshed (synced to scrape cycle)
- Slot card shows a live "Checked Xs ago" indicator that ticks every second
- Toast notification on page when a new slot appears
- Telegram alerts sent when new slots are found; message edited when slot disappears
- Multiple Telegram accounts can be linked per subscription via a shareable link
- On unsubscribe, farewell Telegram message sent to all linked accounts
- Subscriptions auto-expire when the target date passes; linked Telegram accounts are notified
- Admin scrape failure alerts: if a URL fails 3 times in a row, a Telegram message is sent to `ADMIN_CHAT_ID`
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
- `checker/worker.py` — polling loop, slot diffing, subscription expiry, Telegram notifications, account-linking listener
- `static/app.js` — registration form, slot polling, "Checked Xs ago" status, toast notifications, Telegram UI
- `templates/index.html` — main page: Register tab and How it works tab
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
| `ADMIN_CHAT_ID` | No | Your Telegram chat ID — receives alert if a URL fails to scrape 3 times in a row |

## Notes

- `data/` is gitignored and created at runtime; mount it as a Docker volume
- `app/areas.py` is the only place to add new SwiftQueue locations
- On first registration for a URL, the web process immediately scrapes SwiftQueue and seeds both `active_slots` and `area_meta` — no 60s wait
- Frontend polls `/slots/<token>` on a dynamic schedule: 5s after each expected scrape, based on `area_meta.last_scraped_at`
- The immediate web scrape and the checker's first run for that URL may happen ~0–60s apart depending on where the checker is in its cycle — this is expected
- SQLite WAL mode is enabled so both services can read/write concurrently without locking
- Telegram linking is per-token; multiple chat_ids can link via a shareable `/start <token>` link
- Re-subscribing after unsubscribing creates a new token — Telegram must be re-linked
- Subscription expiry runs at the top of every checker cycle; expired subscriptions are deactivated and Telegram accounts notified
