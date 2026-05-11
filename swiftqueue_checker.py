"""
SwiftQueue date checker

Reads config from environment variables (or .env file).
Runs two threads:
  - Checker : polls SwiftQueue every 60s, alerts on early slots
  - Listener: long-polls Telegram, auto-registers any device that messages the bot
"""

import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ── Environment ───────────────────────────────────────────────────────────────

TOKEN       = os.environ.get("TELEGRAM_TOKEN", "")
TARGET_RAW  = os.environ.get("TARGET_DATE", "")     # DD/MM/YYYY
URL         = os.environ.get("SWIFTQUEUE_URL", "https://www.swiftqueue.co.uk/wigan.php")
CHECK_EVERY = 60

# ── Persistence ───────────────────────────────────────────────────────────────

CONFIG_FILE  = Path(__file__).parent / "config" / "config.json"
_chat_ids: list[dict] = []  # [{"id": "...", "name": "..."}]
_lock = threading.Lock()


def _load_chat_ids() -> None:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            for entry in data.get("chat_ids", []):
                if isinstance(entry, str):
                    _chat_ids.append({"id": entry, "name": "Unknown"})
                else:
                    _chat_ids.append(entry)
        except Exception:
            pass


def _save_chat_ids() -> None:
    CONFIG_FILE.write_text(json.dumps({"chat_ids": _chat_ids}, indent=2))


def _register(chat_id: str, name: str) -> None:
    with _lock:
        if any(e["id"] == chat_id for e in _chat_ids):
            return
        _chat_ids.append({"id": chat_id, "name": name})
        _save_chat_ids()
    log.info("Registered %s (%s)", name, chat_id)
    _send(
        [{"id": chat_id, "name": name}],
        "You're registered! You'll receive alerts when a SwiftQueue slot becomes available.",
    )


# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Telegram ──────────────────────────────────────────────────────────────────

HEADERS_FETCH = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def _send(chat_ids: list[dict], message: str) -> dict[str, int]:
    """Returns {chat_id: message_id} for each successfully sent message."""
    if not chat_ids:
        return {}
    api = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    sent = {}
    for cid in [e["id"] for e in chat_ids]:
        try:
            r = requests.post(
                api,
                json={"chat_id": cid, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
            if r.ok:
                sent[cid] = r.json()["result"]["message_id"]
            else:
                log.warning("Telegram error (%s): %s", cid, r.text)
        except Exception as e:
            log.warning("Telegram send failed (%s): %s", cid, e)
    return sent


def _edit(chat_message_ids: dict[str, int], message: str) -> None:
    api = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    for cid, mid in chat_message_ids.items():
        try:
            r = requests.post(
                api,
                json={"chat_id": cid, "message_id": mid, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
            if not r.ok:
                log.warning("Telegram edit error (%s): %s", cid, r.text)
        except Exception as e:
            log.warning("Telegram edit failed (%s): %s", cid, e)


# ── Listener thread ───────────────────────────────────────────────────────────

def _get_initial_offset() -> int:
    """Skip any messages that arrived before this run."""
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            timeout=10,
        )
        results = r.json().get("result", [])
        if results:
            return results[-1]["update_id"] + 1
    except Exception:
        pass
    return 0


def run_listener() -> None:
    offset = _get_initial_offset()
    log.info("Listener started — message the bot from any device to register it.")
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            for update in r.json().get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or update.get("channel_post") or {}
                chat = msg.get("chat", {})
                cid = str(chat.get("id", ""))
                name = chat.get("first_name") or chat.get("title") or "Unknown"
                if cid:
                    _register(cid, name)
        except Exception as e:
            log.warning("Listener error: %s", e)
            time.sleep(5)


# ── Checker thread ────────────────────────────────────────────────────────────

TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def fetch_slots() -> list[tuple[datetime, str, str]]:
    resp = requests.get(URL, headers=HEADERS_FETCH, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    current_clinic = "Unknown clinic"
    last_time = ""

    for tag in soup.find_all(["h3", "h4"]):
        if tag.name == "h3":
            text = tag.get_text(strip=True)
            if "Next available" not in text:
                current_clinic = text
                last_time = ""
        elif tag.name == "h4":
            text = tag.get_text(strip=True)
            if TIME_RE.match(text):
                last_time = text
            else:
                try:
                    dt = datetime.strptime(text, "%d-%m-%Y")
                    results.append((dt, last_time, current_clinic))
                    last_time = ""
                except ValueError:
                    pass

    return results


def run_checker(target: datetime) -> None:
    alerted: dict[tuple, dict[str, int]] = {}  # slot -> {chat_id: message_id}
    log.info("Checker started — watching for slots on or before %s.", target.strftime("%d %b %Y"))

    while True:
        try:
            slots = fetch_slots()
            early = [(dt, t, c) for dt, t, c in slots if dt <= target]
            early_set = set(early)

            gone = [slot for slot in alerted if slot not in early_set]
            for slot in gone:
                dt, t, c = slot
                log.info("Slot gone — editing alert: %s at %s — %s", dt.strftime("%d %b %Y"), t, c)
                _edit(
                    alerted.pop(slot),
                    f"❌ <b>No longer available</b>\n\n<s>{dt.strftime('%d %b %Y')} at {t} — {c}</s>",
                )

            if not early:
                earliest = min(slots, key=lambda x: x[0])[0].strftime("%d-%m-%Y") if slots else "none"
                log.info("No early slots. Earliest available: %s", earliest)
            else:
                new = [s for s in early if s not in alerted]
                if new:
                    log.info("ALERT — %d new slot(s) found:", len(new))
                    with _lock:
                        recipients = list(_chat_ids)
                    for slot in sorted(new):
                        dt, t, c = slot
                        log.info("  • %s at %s — %s", dt.strftime("%d %b %Y"), t, c)
                        sent = _send(
                            recipients,
                            f"🗓 <b>SwiftQueue slot available!</b>\n\n{dt.strftime('%d %b %Y')} at {t} — {c}\n\n"
                            f"<a href=\"{URL}\">Book now →</a>",
                        )
                        alerted[slot] = sent
                else:
                    log.info("%d early slot(s) — already alerted.", len(early))

        except Exception as e:
            log.warning("Checker error: %s", e)

        time.sleep(CHECK_EVERY)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    errors = []
    if not TOKEN:
        errors.append("TELEGRAM_TOKEN is not set.")
    if not TARGET_RAW:
        errors.append("TARGET_DATE is not set.")
    else:
        try:
            target = datetime.strptime(TARGET_RAW, "%d/%m/%Y")
        except ValueError:
            errors.append(f"TARGET_DATE '{TARGET_RAW}' is invalid — use DD/MM/YYYY.")

    if errors:
        for e in errors:
            log.error(e)
        raise SystemExit(1)

    _load_chat_ids()
    log.info("Loaded %d registered device(s).", len(_chat_ids))

    threading.Thread(target=run_listener, daemon=True, name="listener").start()
    run_checker(target)  # runs on main thread


if __name__ == "__main__":
    main()
