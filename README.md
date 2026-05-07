# SwiftQueue Checker

My partner was sent for blood tests by her GP. The earliest slot available was over four weeks away. The GP mentioned that cancellations do come up and you can get lucky with something sooner, so she booked the four-week slot as a backup and I built this to watch for earlier ones.

Within 30 minutes we had a next-day appointment. We actually did several hops — each time a closer slot appeared, she'd book it and immediately cancel the previous one to free it up for someone else. The end result was a next-day appointment, and every slot we vacated along the way went back into the pool.

My partner also wanted alerts on her phone, so I added automatic device registration — just message the bot and you're on the list. No config changes or restarts needed.

If you use this and book an earlier slot, please cancel your old one. Someone else might be in the same boat.

---

SwiftQueue Checker monitors a SwiftQueue location and sends a Telegram alert the moment a slot appears before your target date. Runs in Docker — no Python setup required.

Any device that messages your bot gets automatically registered and will receive alerts. No config changes or restarts needed.

## Example alert

```
🗓 SwiftQueue slot available!

  • 11 May 2026 at 11:25 — Wrightington Discharge Lounge Blood Test
  • 19 May 2026 at 09:40 — Bridgewater Medical Centre Blood Test

Book now →
```

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- A Telegram account

## Quick start

**1. Create a Telegram bot**

Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, and copy the token it gives you.

**2. Clone and configure**

```bash
git clone https://github.com/your-username/swiftqueue-checker
cd swiftqueue-checker
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_TOKEN=your_bot_token_here
TARGET_DATE=19/05/2026
```

**3. Start**

```bash
docker-compose up -d
```

**4. Register your device**

Send any message to your bot in Telegram. It will reply confirming you're registered. Repeat from any other device or person you want to alert — no restart needed.

That's it. The checker runs in the background and pings everyone the moment a slot opens up.

---

## How it works

Two processes run continuously inside the container:

| Thread | What it does |
|---|---|
| **Checker** | Polls SwiftQueue every 60 seconds. Sends a Telegram alert when a slot is found on or before your target date. |
| **Listener** | Long-polls the Telegram bot. Any time someone sends the bot a message, their chat ID and display name are saved to `config.json` and they're added to the alert list immediately. |

Registered devices are stored in `config.json` and persist across container restarts. Each entry includes the Telegram display name at the time of registration so you can tell who's who:

```json
{
  "chat_ids": [
    {"id": "123456789", "name": "Joe"},
    {"id": "987654321", "name": "Sarah"}
  ]
}
```

## Available locations

Set `SWIFTQUEUE_URL` in your `.env` to the URL for your area:

| Name on site | URL |
|---|---|
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

Don't see your area? SwiftQueue URLs follow the pattern `https://www.swiftqueue.co.uk/<slug>.php` — try searching `site:swiftqueue.co.uk` on Google, or raise a PR to add it to this list.

## Configuration

| File | Purpose |
|---|---|
| `.env` | Your bot token, target date, and location — keep this private, don't commit it |
| `config.json` | Auto-managed list of registered chat IDs and display names |

To change your target date or location, update `.env` and restart the container:

```bash
docker-compose restart
```

To remove a device, delete their entry from `config.json`. The container picks up the change on next restart.

## Running without Docker

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows
# .venv/bin/pip install -r requirements.txt     # Mac / Linux

cp .env.example .env   # fill in your values

.venv/Scripts/python swiftqueue_checker.py      # Windows
# .venv/bin/python swiftqueue_checker.py        # Mac / Linux
```

## Logs

```bash
docker-compose logs -f
```

```
10:01:00  Loaded 2 registered device(s).
10:01:00  Listener started — message the bot from any device to register it.
10:01:00  Checker started — watching for slots on or before 19 May 2026.
10:01:02  No early slots. Earliest available: 19-05-2026
10:02:02  ALERT — 1 new slot(s) found:
            • 11 May 2026 at 11:25 — Wrightington Discharge Lounge Blood Test
```
