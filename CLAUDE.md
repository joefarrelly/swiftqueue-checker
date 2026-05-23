# SwiftQueue Checker

A Flask web app that polls SwiftQueue for appointment slots earlier than each user's target date, and delivers browser push notifications (with optional Telegram backup).

## What it does

- Users register via the web UI: pick an area, set a target date, grant push permission
- Browser push notification fires when a slot on or before their target date appears
- Optionally links a Telegram account for backup alerts
- Checker polls all watched SwiftQueue URLs every 60s (staggered, one per second)
- Slot state persisted in SQLite so restarts don't cause duplicate alerts

## Architecture

Two Docker services sharing a SQLite database (`data/swiftqueue.db`):

- **web** — Flask app (gunicorn), handles registration/unsubscribe UI and push subscription
- **checker** — background poller, diffs slots against DB state, dispatches notifications

## Key files

- `app/__init__.py` — Flask app factory
- `app/db.py` — SQLite schema, `get_db()` context manager, `init_db()`
- `app/areas.py` — curated dict of `{name: url}` for the area dropdown
- `app/scraper.py` — `fetch_slots(url)` HTML parser (if SwiftQueue changes structure, check here)
- `app/notifications.py` — `send_push()` via pywebpush, `send_telegram()` via Bot API
- `app/routes.py` — Flask routes: `/`, `/register`, `/unsubscribe/<token>`, `/vapid-public-key`
- `checker/worker.py` — polling loop, slot diffing, Telegram account-linking listener
- `static/sw.js` — service worker: handles push events and notification clicks
- `static/app.js` — registration form, push subscription flow
- `templates/index.html` — registration page
- `templates/unsubscribe.html` — unsubscribe confirmation

## Setup

```bash
cp .env.example .env
# fill in .env (see below)
```

Generate VAPID keys (required for push notifications):
```bash
npx web-push generate-vapid-keys
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
| `VAPID_PUBLIC_KEY` | Yes | Web push VAPID public key |
| `VAPID_PRIVATE_KEY` | Yes | Web push VAPID private key |
| `VAPID_CLAIMS_EMAIL` | Yes | `mailto:you@example.com` |
| `TELEGRAM_TOKEN` | No | Bot token — enables Telegram alerts |
| `TELEGRAM_BOT_USERNAME` | No | e.g. `MySwiftQueueBot` — shows Link Telegram button |

## Notes

- `data/` is gitignored and created at runtime; mount it as a Docker volume
- `app/areas.py` is the only place to add new SwiftQueue locations
- On registration, the web process immediately checks `active_slots` in the DB and notifies if qualifying slots are already known — no 60s wait for first-time users
- SQLite WAL mode is enabled so both services can read/write concurrently without locking
