# SwiftQueue Checker

**Live at [queue4me.uk](https://queue4me.uk)**

My partner was sent for blood tests by her GP. The earliest slot available was over four weeks away. The GP mentioned that cancellations do come up and you can get lucky with something sooner, so she booked the four-week slot as a backup and I built this to watch for earlier ones.

Within 30 minutes we had a next-day appointment. We actually did several hops — each time a closer slot appeared, she'd book it and immediately cancel the previous one to free it up for someone else. The end result was a next-day appointment, and every slot we vacated along the way went back into the pool.

If you use this and book an earlier slot, please cancel your old one. Someone else might be in the same boat.

---

SwiftQueue Checker is a web app that watches SwiftQueue for appointment slots before your target date. Multiple people can watch the same or different areas simultaneously. Slots appear on the page as soon as they're found, with optional Telegram alerts.

## How it works

- Register via the web UI: search for your area and set a target date
- Available slots matching your criteria appear on the page and update automatically, with a live "last checked" indicator
- Optionally link a Telegram account to receive alerts directly in Telegram
- Multiple Telegram accounts can link to the same registration — share the link with anyone who should also get notified
- The background checker polls all watched areas every 60 seconds
- When a slot disappears, the corresponding Telegram message is edited to show it's gone
- When your target date passes, your subscription is automatically cancelled and you'll receive a Telegram notification

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
ADMIN_CHAT_ID=your_chat_id               # optional, scrape failure alerts
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
| `ADMIN_CHAT_ID` | No | Your Telegram chat ID — receives an alert if a URL fails to scrape 3 times in a row |

## Available locations

32 areas currently supported. The area dropdown on the page is searchable — start typing to filter.

| Area |
|------|
| Barking, Havering and Redbridge University Hospitals |
| Buckinghamshire Healthcare NHS Trust |
| Coventry and Warwickshire Blood Tests |
| East London NHS Phlebotomy Clinics |
| East Sussex Phlebotomy |
| Frimley Health NHS Foundation Trust Bloods |
| Hertfordshire Community NHS Trust |
| Homerton Healthcare NHS Foundation Trust |
| Lewisham and Greenwich NHS Trust |
| Medway Phlebotomy Network |
| Mid Essex Phlebotomy Network |
| NELFT Barking, Dagenham, Havering and Redbridge |
| NELFT Waltham Forest Phlebotomy |
| Newham University Hospital Phlebotomy |
| North Middlesex University Hospital Blood Tests |
| North Warwickshire Blood Test Clinics |
| Northampton General Hospital Network |
| Pathology First Blood Test Clinic Network |
| Plymouth Adult Blood Test |
| Princess Alexandra Hospital, Harlow |
| Royal Berkshire Blood Tests |
| Royal Free London NHS Foundation Trust |
| Royal Surrey Hospital NHS Foundation Trust |
| Surrey and Sussex Healthcare NHS Trust |
| Synnovis GP Referral (King's, Guy's & St Thomas') |
| Synnovis Outpatient Phlebotomy (King's, Guy's & St Thomas') |
| University College London Hospitals |
| University Hospitals of Derby and Burton |
| West Hertfordshire Teaching Hospitals |
| West Suffolk NHS |
| Whittington Health NHS Trust |
| Wrightington, Wigan and Leigh NHS Phlebotomy Clinics |

Don't see your area? Open an issue or raise a PR — SwiftQueue URLs follow the pattern `https://www.swiftqueue.co.uk/<slug>.php`. Add it to `app/areas.py`.

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

---

Found a bug or your area isn't listed? [Open an issue on GitHub](https://github.com/joefarrelly/swiftqueue-checker/issues).
