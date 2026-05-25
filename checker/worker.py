"""Background checker — polls SwiftQueue URLs and dispatches notifications."""

import logging
import os
import threading
import time
from datetime import datetime, timezone

import requests

from app.areas import AREAS
from app.db import get_db, init_db
from app.notifications import edit_telegram_message, send_push, send_telegram
from app.scraper import fetch_slots

log = logging.getLogger(__name__)

_TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
_ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
_CHECK_EVERY = 60
_SCRAPE_FAIL_THRESHOLD = 3

_scrape_failures: dict[str, int] = {}


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


def _telegram_message_text(body: str, url: str) -> str:
    return f'🗓 <b>SwiftQueue slot available!</b>\n\n{body}\n\n<a href="{url}">Book now →</a>'


def _telegram_gone_text(body: str) -> str:
    return f"❌ <b>Slot no longer available</b>\n\n<s>{body}</s>"


def _store_telegram_message(
    token: str,
    chat_id: str,
    message_id: int,
    url: str,
    slot_date: str,
    slot_time: str,
    clinic: str,
) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO telegram_messages
               (token, chat_id, message_id, area_url, slot_date, slot_time, clinic)
               VALUES (?,?,?,?,?,?,?)""",
            (token, chat_id, message_id, url, slot_date, slot_time, clinic),
        )


# ── Subscription expiry ───────────────────────────────────────────────────────


def _expire_stale_subscriptions() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    notifications: list[tuple[str, str]] = []
    with get_db() as conn:
        expired = conn.execute(
            "SELECT token, area_url, target_date FROM users WHERE active=1 AND target_date < ?",
            (today,),
        ).fetchall()
        if not expired:
            return
        for user in expired:
            token = user["token"]
            area_name = next(
                (k for k, v in AREAS.items() if v == user["area_url"]),
                user["area_url"],
            )
            target_friendly = datetime.strptime(
                user["target_date"], "%Y-%m-%d"
            ).strftime("%-d %B %Y")
            subscribers = conn.execute(
                "SELECT chat_id FROM telegram_subscribers WHERE token=?",
                (token,),
            ).fetchall()
            conn.execute("UPDATE users SET active=0 WHERE token=?", (token,))
            conn.execute("DELETE FROM telegram_subscribers WHERE token=?", (token,))
            conn.execute("DELETE FROM telegram_messages WHERE token=?", (token,))
            log.info(
                "Expired subscription %s (target date %s passed)",
                token,
                user["target_date"],
            )
            msg = (
                f"⏰ Your target date of {target_friendly} for <b>{area_name}</b> has passed, "
                f"so we've stopped watching for slots.\n\n"
                f"Visit the website if you'd like to register for a new date."
            )
            for sub in subscribers:
                notifications.append((sub["chat_id"], msg))
    for chat_id, msg in notifications:
        send_telegram(chat_id, msg)


# ── Poll ──────────────────────────────────────────────────────────────────────


def _poll_url(url: str, previous: dict[str, set[tuple[str, str, str]]]) -> None:
    try:
        slots = fetch_slots(url)
        current = {(dt.strftime("%Y-%m-%d"), t, c) for dt, t, c, _u in slots}
        booking_urls = {(dt.strftime("%Y-%m-%d"), t, c): _u for dt, t, c, _u in slots}
        if url not in previous:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT slot_date, slot_time, clinic FROM active_slots WHERE url=?",
                    (url,),
                ).fetchall()
            previous[url] = {
                (r["slot_date"], r["slot_time"], r["clinic"]) for r in rows
            }
        prev = previous[url]
        new_slots = current - prev
        gone_slots = prev - current
        now = datetime.now(timezone.utc).isoformat()

        for slot_date, slot_time, clinic in sorted(new_slots):
            users = _get_users_for_slot(url, slot_date)
            if not users:
                continue
            dt_display = datetime.strptime(slot_date, "%Y-%m-%d").strftime("%d %b %Y")
            body = f"{dt_display} at {slot_time} — {clinic}"
            log.info("New slot: %s @ %s — notifying %d user(s)", body, url, len(users))
            for user in users:
                with get_db() as conn:
                    subscribers = conn.execute(
                        "SELECT chat_id FROM telegram_subscribers WHERE token=?",
                        (user["token"],),
                    ).fetchall()
                booking_url = booking_urls.get((slot_date, slot_time, clinic), url)
                for sub in subscribers:
                    msg_id = send_telegram(
                        sub["chat_id"], _telegram_message_text(body, booking_url)
                    )
                    if msg_id:
                        _store_telegram_message(
                            user["token"],
                            sub["chat_id"],
                            msg_id,
                            url,
                            slot_date,
                            slot_time,
                            clinic,
                        )
                if user.get("push_subscription"):
                    still_active = send_push(
                        user["push_subscription"],
                        "SwiftQueue slot available!",
                        body,
                        booking_url,
                    )
                    if not still_active:
                        with get_db() as conn:
                            conn.execute(
                                "UPDATE users SET push_subscription=NULL WHERE token=?",
                                (user["token"],),
                            )

        with get_db() as conn:
            for slot_date, slot_time, clinic in new_slots:
                conn.execute(
                    """INSERT OR IGNORE INTO active_slots
                       (url, slot_date, slot_time, clinic, booking_url, first_seen_at, seen_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        url,
                        slot_date,
                        slot_time,
                        clinic,
                        booking_urls.get((slot_date, slot_time, clinic), ""),
                        now,
                        now,
                    ),
                )
            for slot_date, slot_time, clinic in current & prev:
                conn.execute(
                    """UPDATE active_slots SET seen_at=?, booking_url=?
                       WHERE url=? AND slot_date=? AND slot_time=? AND clinic=?""",
                    (
                        now,
                        booking_urls.get((slot_date, slot_time, clinic), ""),
                        url,
                        slot_date,
                        slot_time,
                        clinic,
                    ),
                )
            for slot_date, slot_time, clinic in gone_slots:
                conn.execute(
                    """DELETE FROM active_slots
                       WHERE url=? AND slot_date=? AND slot_time=? AND clinic=?""",
                    (url, slot_date, slot_time, clinic),
                )
                msgs = conn.execute(
                    """SELECT chat_id, message_id FROM telegram_messages
                       WHERE area_url=? AND slot_date=? AND slot_time=? AND clinic=?""",
                    (url, slot_date, slot_time, clinic),
                ).fetchall()
                dt_display = datetime.strptime(slot_date, "%Y-%m-%d").strftime(
                    "%d %b %Y"
                )
                gone_body = f"{dt_display} at {slot_time} — {clinic}"
                for msg in msgs:
                    edit_telegram_message(
                        msg["chat_id"],
                        msg["message_id"],
                        _telegram_gone_text(gone_body),
                    )
                conn.execute(
                    """DELETE FROM telegram_messages
                       WHERE area_url=? AND slot_date=? AND slot_time=? AND clinic=?""",
                    (url, slot_date, slot_time, clinic),
                )

        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO area_meta (url, last_scraped_at) VALUES (?,?)",
                (url, now),
            )
        previous[url] = current
        _scrape_failures[url] = 0

    except Exception as e:
        log.warning("Poll error for %s: %s", url, e)
        _scrape_failures[url] = _scrape_failures.get(url, 0) + 1
        if _scrape_failures[url] == _SCRAPE_FAIL_THRESHOLD and _ADMIN_CHAT_ID:
            send_telegram(
                _ADMIN_CHAT_ID,
                f"⚠️ <b>Scrape failing</b>\n\n{url}\n\nhas failed {_SCRAPE_FAIL_THRESHOLD} times in a row.\n\n{e}",
            )


# ── Telegram helpers ─────────────────────────────────────────────────────────


def _send_current_slots_to_telegram(token: str, chat_id: str) -> None:
    """Send all currently available matching slots to a newly linked Telegram account."""
    try:
        with get_db() as conn:
            user = conn.execute(
                "SELECT area_url, target_date FROM users WHERE token=? AND active=1",
                (token,),
            ).fetchone()
            if not user:
                return
            slots = conn.execute(
                """SELECT slot_date, slot_time, clinic, booking_url FROM active_slots
                   WHERE url=? AND slot_date <= ?
                   ORDER BY slot_date, slot_time""",
                (user["area_url"], user["target_date"]),
            ).fetchall()
        for slot in slots:
            dt_display = datetime.strptime(slot["slot_date"], "%Y-%m-%d").strftime(
                "%d %b %Y"
            )
            body = f"{dt_display} at {slot['slot_time']} — {slot['clinic']}"
            booking_url = slot["booking_url"] or user["area_url"]
            msg_id = send_telegram(chat_id, _telegram_message_text(body, booking_url))
            if msg_id:
                _store_telegram_message(
                    token,
                    chat_id,
                    msg_id,
                    user["area_url"],
                    slot["slot_date"],
                    slot["slot_time"],
                    slot["clinic"],
                )
    except Exception as e:
        log.warning("_send_current_slots_to_telegram error: %s", e)


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
                if not chat_id:
                    continue
                if text.strip() == "/start":
                    send_telegram(
                        chat_id,
                        "⚠️ No token found. Please use the link from the SwiftQueue Checker website to link your account.",
                    )
                    continue
                if not text.startswith("/start "):
                    continue
                token = text.split(" ", 1)[1].strip()
                if not token:
                    send_telegram(
                        chat_id,
                        "⚠️ No token found. Please use the link from the SwiftQueue Checker website to link your account.",
                    )
                    continue
                with get_db() as conn:
                    user = conn.execute(
                        "SELECT area_url, target_date FROM users WHERE token=? AND active=1",
                        (token,),
                    ).fetchone()
                    if not user:
                        continue
                    existing = conn.execute(
                        "SELECT token FROM telegram_subscribers WHERE chat_id=?",
                        (chat_id,),
                    ).fetchall()
                    existing_tokens = {r["token"] for r in existing}
                    if existing_tokens == {token}:
                        already_linked = True
                        prev_area_name = None
                    elif token in existing_tokens:
                        # linked to this token plus others — clean up the others
                        already_linked = False
                        prev_area_name = None
                        prev_target_friendly = None
                        for old_token in existing_tokens - {token}:
                            conn.execute(
                                "DELETE FROM telegram_subscribers WHERE token=? AND chat_id=?",
                                (old_token, chat_id),
                            )
                    elif existing_tokens:
                        # linked to a different subscription — switch
                        already_linked = False
                        old_token = next(iter(existing_tokens))
                        old_user = conn.execute(
                            "SELECT area_url, target_date FROM users WHERE token=?",
                            (old_token,),
                        ).fetchone()
                        if old_user:
                            prev_area_name = next(
                                (
                                    k
                                    for k, v in AREAS.items()
                                    if v == old_user["area_url"]
                                ),
                                old_user["area_url"],
                            )
                            prev_target_friendly = datetime.strptime(
                                old_user["target_date"], "%Y-%m-%d"
                            ).strftime("%-d %B %Y")
                        else:
                            prev_area_name = None
                            prev_target_friendly = None
                        conn.execute(
                            "DELETE FROM telegram_subscribers WHERE chat_id=?",
                            (chat_id,),
                        )
                    else:
                        already_linked = False
                        prev_area_name = None
                        prev_target_friendly = None
                    if not already_linked:
                        conn.execute(
                            "INSERT OR IGNORE INTO telegram_subscribers (token, chat_id) VALUES (?,?)",
                            (token, chat_id),
                        )
                area_name = next(
                    (k for k, v in AREAS.items() if v == user["area_url"]),
                    user["area_url"],
                )
                target_friendly = datetime.strptime(
                    user["target_date"], "%Y-%m-%d"
                ).strftime("%-d %B %Y")
                watching_text = (
                    f"You're watching <b>{area_name}</b>"
                    f" for slots on or before {target_friendly}."
                )
                if already_linked:
                    send_telegram(chat_id, f"ℹ️ Already linked! {watching_text}")
                    continue
                log.info("Linked Telegram chat %s via token", chat_id)
                if prev_area_name:
                    prev_detail = (
                        f" for slots on or before {prev_target_friendly}"
                        if prev_target_friendly
                        else ""
                    )
                    send_telegram(
                        chat_id,
                        f"🔄 Switched! You were previously watching <b>{prev_area_name}</b>{prev_detail}.\n\n"
                        f"✅ {watching_text}",
                    )
                else:
                    send_telegram(chat_id, f"✅ Telegram linked! {watching_text}")
                _send_current_slots_to_telegram(token, chat_id)
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
        _expire_stale_subscriptions()
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
