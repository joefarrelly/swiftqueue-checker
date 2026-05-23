"""Background checker — polls SwiftQueue URLs and dispatches notifications."""

import logging
import os
import threading
import time
from datetime import datetime, timezone

import requests

from app.db import get_db, init_db
from app.notifications import send_push, send_telegram
from app.scraper import fetch_slots

log = logging.getLogger(__name__)

_TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
_CHECK_EVERY = 60


# ── DB helpers ────────────────────────────────────────────────────────────────


def _load_previous_slots() -> dict[str, set[tuple[str, str, str]]]:
    previous: dict[str, set[tuple[str, str, str]]] = {}
    with get_db() as conn:
        rows = conn.execute(
            "SELECT url, slot_date, slot_time, clinic FROM active_slots"
        ).fetchall()
    for row in rows:
        url = row["url"]
        if url not in previous:
            previous[url] = set()
        previous[url].add((row["slot_date"], row["slot_time"], row["clinic"]))
    return previous


def _get_watched_urls() -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT area_url FROM users WHERE active=1"
        ).fetchall()
    return [row["area_url"] for row in rows]


def _get_users_for_slot(url: str, slot_date: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE area_url=? AND target_date>=? AND active=1",
            (url, slot_date),
        ).fetchall()
    return [dict(row) for row in rows]


# ── Poll ──────────────────────────────────────────────────────────────────────


def _poll_url(url: str, previous: dict[str, set[tuple[str, str, str]]]) -> None:
    try:
        slots = fetch_slots(url)
        current = {(dt.strftime("%Y-%m-%d"), t, c) for dt, t, c in slots}
        prev = previous.get(url, set())
        new_slots = current - prev
        gone_slots = prev - current
        now = datetime.now(timezone.utc).isoformat()

        for slot_date, slot_time, clinic in sorted(new_slots):
            users = _get_users_for_slot(url, slot_date)
            if not users:
                continue
            dt_display = datetime.strptime(slot_date, "%Y-%m-%d").strftime("%d %b %Y")
            body = f"{dt_display} at {slot_time} — {clinic}"
            log.info("New slot: %s @ %s", body, url)
            for user in users:
                if user["push_subscription"]:
                    send_push(
                        user["push_subscription"],
                        "SwiftQueue slot available!",
                        body,
                        url,
                    )
                if user["telegram_chat_id"]:
                    send_telegram(
                        user["telegram_chat_id"],
                        f"🗓 <b>SwiftQueue slot available!</b>\n\n{body}\n\n"
                        f'<a href="{url}">Book now →</a>',
                    )

        with get_db() as conn:
            for slot_date, slot_time, clinic in new_slots:
                conn.execute(
                    """INSERT OR IGNORE INTO active_slots
                       (url, slot_date, slot_time, clinic, first_seen_at, seen_at)
                       VALUES (?,?,?,?,?,?)""",
                    (url, slot_date, slot_time, clinic, now, now),
                )
            for slot_date, slot_time, clinic in current & prev:
                conn.execute(
                    """UPDATE active_slots SET seen_at=?
                       WHERE url=? AND slot_date=? AND slot_time=? AND clinic=?""",
                    (now, url, slot_date, slot_time, clinic),
                )
            for slot_date, slot_time, clinic in gone_slots:
                conn.execute(
                    """DELETE FROM active_slots
                       WHERE url=? AND slot_date=? AND slot_time=? AND clinic=?""",
                    (url, slot_date, slot_time, clinic),
                )

        previous[url] = current

    except Exception as e:
        log.warning("Poll error for %s: %s", url, e)


# ── Telegram account-linking listener ────────────────────────────────────────


def _run_telegram_listener() -> None:
    """Handles /start <token> messages to link Telegram accounts."""
    offset = 0
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/getUpdates",
            timeout=10,
        )
        results = r.json().get("result", [])
        if results:
            offset = results[-1]["update_id"] + 1
    except Exception:
        pass

    log.info("Telegram listener started for account linking.")
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            for update in r.json().get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if not chat_id or not text.startswith("/start "):
                    continue
                token = text.split(" ", 1)[1].strip()
                with get_db() as conn:
                    result = conn.execute(
                        "UPDATE users SET telegram_chat_id=? WHERE token=? AND active=1",
                        (chat_id, token),
                    )
                if result.rowcount:
                    log.info("Linked Telegram chat %s via token", chat_id)
                    requests.post(
                        f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": "✅ Telegram linked! You'll receive SwiftQueue alerts here.",
                        },
                        timeout=10,
                    )
        except Exception as e:
            log.warning("Telegram listener error: %s", e)
            time.sleep(5)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    from dotenv import load_dotenv

    load_dotenv()

    init_db()

    previous = _load_previous_slots()
    log.info(
        "Checker started — %d slot(s) loaded from DB as initial state.",
        sum(len(v) for v in previous.values()),
    )

    if _TELEGRAM_TOKEN:
        threading.Thread(
            target=_run_telegram_listener,
            daemon=True,
            name="telegram-listener",
        ).start()

    while True:
        urls = _get_watched_urls()
        for i, url in enumerate(urls):
            if i > 0:
                time.sleep(1)
            _poll_url(url, previous)
        if not urls:
            log.debug("No active users — idling.")
        time.sleep(_CHECK_EVERY)


if __name__ == "__main__":
    main()
