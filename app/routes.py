import logging
import os
import secrets
import threading
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request

from app.areas import AREAS
from app.db import get_db
from app.notifications import send_telegram
from app.scraper import fetch_slots

log = logging.getLogger(__name__)

bp = Blueprint("main", __name__)


@bp.route("/sw.js")
def service_worker():
    from flask import current_app

    return current_app.send_static_file("sw.js")


@bp.route("/")
def index():
    return render_template(
        "index.html",
        areas=AREAS,
        telegram_bot=os.environ.get("TELEGRAM_BOT_USERNAME", ""),
    )


@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    area_url = data.get("area_url", "").strip()
    target_date = data.get("target_date", "").strip()

    if area_url not in AREAS.values():
        return jsonify({"error": "Invalid area"}), 400
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date — use YYYY-MM-DD"}), 400

    token = secrets.token_urlsafe(32)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users (token, area_url, target_date) VALUES (?,?,?)",
            (token, area_url, target_date),
        )

    with get_db() as conn:
        other_active = conn.execute(
            "SELECT COUNT(*) FROM users WHERE area_url=? AND active=1 AND token!=?",
            (area_url, token),
        ).fetchone()[0]

    threading.Thread(
        target=_notify_existing_slots,
        args=(token, area_url, target_dt, other_active == 0),
        daemon=True,
    ).start()

    return jsonify({"token": token})


@bp.route("/registration/<token>")
def registration(token: str):
    with get_db() as conn:
        user = conn.execute(
            "SELECT area_url, target_date FROM users WHERE token=? AND active=1",
            (token,),
        ).fetchone()
    if not user:
        return jsonify({"error": "not found"}), 404
    area_name = next(
        (k for k, v in AREAS.items() if v == user["area_url"]), user["area_url"]
    )
    with get_db() as conn:
        telegram_linked = bool(
            conn.execute(
                "SELECT 1 FROM telegram_subscribers WHERE token=?", (token,)
            ).fetchone()
        )
    return jsonify(
        {
            "area_name": area_name,
            "target_date": user["target_date"],
            "telegram_linked": telegram_linked,
        }
    )


@bp.route("/status")
def status():
    with get_db() as conn:
        watched = conn.execute(
            """SELECT area_url, COUNT(*) as user_count
               FROM users WHERE active=1
               GROUP BY area_url"""
        ).fetchall()
        slots = conn.execute(
            """SELECT url, slot_date, slot_time, clinic, first_seen_at, seen_at
               FROM active_slots
               ORDER BY url, slot_date, slot_time"""
        ).fetchall()
    return render_template("status.html", watched=watched, slots=slots)


@bp.route("/slots/<token>")
def slots(token: str):
    with get_db() as conn:
        user = conn.execute(
            "SELECT area_url, target_date FROM users WHERE token=? AND active=1",
            (token,),
        ).fetchone()
        if not user:
            return jsonify({"slots": [], "last_scraped_at": None})
        rows = conn.execute(
            """SELECT slot_date, slot_time, clinic, booking_url, url as area_url
               FROM active_slots
               WHERE url=? AND slot_date <= ?
               ORDER BY slot_date, slot_time""",
            (user["area_url"], user["target_date"]),
        ).fetchall()
        meta = conn.execute(
            "SELECT last_scraped_at FROM area_meta WHERE url=?",
            (user["area_url"],),
        ).fetchone()
        telegram_linked = bool(
            conn.execute(
                "SELECT 1 FROM telegram_subscribers WHERE token=?", (token,)
            ).fetchone()
        )
    return jsonify(
        {
            "slots": [dict(r) for r in rows],
            "last_scraped_at": meta["last_scraped_at"] if meta else None,
            "telegram_linked": telegram_linked,
        }
    )


@bp.route("/unsubscribe/<token>", methods=["GET", "POST"])
def unsubscribe(token: str):
    with get_db() as conn:
        user = conn.execute(
            "SELECT area_url, target_date FROM users WHERE token=? AND active=1",
            (token,),
        ).fetchone()

    if not user:
        return render_template("unsubscribe.html", done=True, not_found=True)

    area_name = next(
        (k for k, v in AREAS.items() if v == user["area_url"]), user["area_url"]
    )

    if request.method == "POST":
        with get_db() as conn:
            subscribers = [
                r["chat_id"]
                for r in conn.execute(
                    "SELECT chat_id FROM telegram_subscribers WHERE token=?", (token,)
                ).fetchall()
            ]
            conn.execute("DELETE FROM telegram_subscribers WHERE token=?", (token,))
            conn.execute("UPDATE users SET active=0 WHERE token=?", (token,))
            remaining = conn.execute(
                "SELECT COUNT(*) FROM users WHERE area_url=? AND active=1",
                (user["area_url"],),
            ).fetchone()[0]
            if remaining == 0:
                conn.execute(
                    "DELETE FROM active_slots WHERE url=?", (user["area_url"],)
                )
        from datetime import datetime as _dt

        target_friendly = _dt.strptime(user["target_date"], "%Y-%m-%d").strftime(
            "%-d %B %Y"
        )
        for chat_id in subscribers:
            send_telegram(
                chat_id,
                f"👋 You've been unsubscribed from SwiftQueue alerts for <b>{area_name}</b>"
                f" (slots on or before {target_friendly}).",
            )
        if request.accept_mimetypes.accept_json:
            return jsonify({"ok": True})
        return render_template("unsubscribe.html", done=True)

    return render_template(
        "unsubscribe.html",
        token=token,
        done=False,
        area_name=area_name,
        target_date=user["target_date"],
    )


def _notify_existing_slots(
    token: str, area_url: str, target_dt: datetime, scrape_now: bool
) -> None:
    try:
        if scrape_now:
            slots = fetch_slots(area_url)
            now = datetime.now(timezone.utc).isoformat()
            rows = []
            with get_db() as conn:
                for dt, slot_time, clinic, booking_url in slots:
                    slot_date = dt.strftime("%Y-%m-%d")
                    conn.execute(
                        """INSERT OR IGNORE INTO active_slots
                           (url, slot_date, slot_time, clinic, booking_url, first_seen_at, seen_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (area_url, slot_date, slot_time, clinic, booking_url, now, now),
                    )
                    rows.append(
                        {
                            "slot_date": slot_date,
                            "slot_time": slot_time,
                            "clinic": clinic,
                        }
                    )
                conn.execute(
                    "INSERT OR REPLACE INTO area_meta (url, last_scraped_at) VALUES (?,?)",
                    (area_url, now),
                )
            log.info("Immediate scrape for %s found %d slot(s)", area_url, len(rows))
        else:
            with get_db() as conn:
                rows = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT slot_date, slot_time, clinic FROM active_slots WHERE url=?",
                        (area_url,),
                    ).fetchall()
                ]

    except Exception as e:
        log.warning("_notify_existing_slots error: %s", e)
