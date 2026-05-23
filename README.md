# SwiftQueue Checker

My partner was sent for blood tests by her GP. The earliest slot available was over four weeks away. The GP mentioned that cancellations do come up and you can get lucky with something sooner, so she booked the four-week slot as a backup and I built this to watch for earlier ones.

Within 30 minutes we had a next-day appointment. We actually did several hops — each time a closer slot appeared, she'd book it and immediately cancel the previous one to free it up for someone else. The end result was a next-day appointment, and every slot we vacated along the way went back into the pool.

If you use this and book an earlier slot, please cancel your old one. Someone else might be in the same boat.

---

SwiftQueue Checker is a web app that watches SwiftQueue for appointment slots before your target date. Multiple people can watch the same or different areas simultaneously. Slots appear on the page as soon as they're found, with optional Telegram alerts.

## How it works

- Register via the web UI: pick your area and target date
- Available slots matching your criteria appear on the page and update automatically
- Optionally link a Telegram account to receive alerts directly in Telegram
- Multiple Telegram accounts can link to the same registration — share the link with anyone who should also get notified
- The background checker polls all watched areas every 60 seconds
- When a slot disappears, the corresponding Telegram message is edited to show it's gone

## Example Telegram alert

```
🗓 SwiftQueue slot available!

11 May 2026 at 11:25 — Wrightington Discharge Lounge Blood Test

Book now →
```

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- A Telegram bot (optional, but recommended for phone alerts)

## Quick start

**1. Create a Telegram bot** (optional)

Message [@BotFather](https://t.me/BotFather), send `/newbot`, and copy the token it gives you. Also note the username (e.g. `MySwiftQueueBot`).

**2. Clone and configure**

```bash
git clone https://github.com/joefarrelly/swiftqueue-checker
cd swiftqueue-checker
cp .env.example .env
```

Edit `.env`:

```env
SECRET_KEY=a-long-random-string
TELEGRAM_TOKEN=your_bot_token_here        # optional
TELEGRAM_BOT_USERNAME=YourBotUsername     # optional, shows the Link Telegram button
```

**3. Start**

```bash
docker compose up -d
```

The web UI is available at `http://localhost:5000`.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask session secret — any long random string |
| `TELEGRAM_TOKEN` | No | Bot token from BotFather — enables Telegram alerts |
| `TELEGRAM_BOT_USERNAME` | No | e.g. `MySwiftQueueBot` — shows the Link Telegram button in the UI |

## Available locations

| Area | URL |
|------|-----|
| Wrightington, Wigan and Leigh NHS Phlebotomy Clinics | `https://www.swiftqueue.co.uk/wigan.php` |
| Northampton General Hospital Network | `https://www.swiftqueue.co.uk/northampton.php` |
| Coventry and Warwickshire Blood Tests | `https://www.swiftqueue.co.uk/uhcw.php` |
| Medway Phlebotomy Network | `https://www.swiftqueue.co.uk/medway.php` |
| Royal Berkshire Blood Tests | `https://www.swiftqueue.co.uk/royal_berkshire.php` |
| West Suffolk NHS | `https://www.swiftqueue.co.uk/west_suffolk.php` |
| Plymouth Adult Blood Test | `https://www.swiftqueue.co.uk/plymouth_adult_blood_test.php` |
| East London NHS Phlebotomy Clinics | `https://www.swiftqueue.co.uk/elft.php` |
| Whittington Health NHS Trust | `https://www.swiftqueue.co.uk/whittington.php` |
| University College London Hospitals | `https://www.swiftqueue.co.uk/UCLH_CC.php` |
| Frimley Health NHS Foundation Trust Bloods | `https://www.swiftqueue.co.uk/fhftpaeds.php` |
| Lewisham and Greenwich NHS Trust | `https://www.swiftqueue.co.uk/lewisham.php` |
| Newham University Hospital Phlebotomy | `https://www.swiftqueue.co.uk/NUH_Phlebotomy.php` |
| East Sussex Phlebotomy | `https://www.swiftqueue.co.uk/east_sussex_phlebotomy.php` |
| Pathology First Blood Test Clinic Network | `https://www.swiftqueue.co.uk/ippmain.php` |

Don't see your area? Add it to `app/areas.py` — SwiftQueue URLs follow the pattern `https://www.swiftqueue.co.uk/<slug>.php`. Raise a PR to share it.

## Running without Docker

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your values

flask --app "app:create_app()" run    # web (terminal 1)
python -m checker.worker              # checker (terminal 2)
```

## Logs

```bash
docker compose logs -f
```
