import json
import os
import secrets
import threading
from datetime import datetime

from flask import Blueprint, current_app, jsonify, render_template, request

from app.areas import AREAS
from app.db import get_db
from app.notifications import send_push

bp = Blueprint("main", __name__)


@bp.route("/sw.js")
def service_worker():
    return current_app.send_static_file("sw.js")


@bp.route("/")
def index():
    return render_template(
        "index.html",
        areas=AREAS,
        vapid_public_key=current_app.config["VAPID_PUBLIC_KEY"],
        telegram_bot=os.environ.get("TELEGRAM_BOT_USERNAME", ""),
    )


@bp.route("/vapid-public-key")
def vapid_public_key():
    return current_app.config["VAPID_PUBLIC_KEY"]


@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    area_url = data.get("area_url", "").strip()
    target_date = data.get("target_date", "").strip()
    push_subscription = data.get("push_subscription")

    if area_url not in AREAS.values():
        return jsonify({"error": "Invalid area"}), 400
    try:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date — use YYYY-MM-DD"}), 400
    if push_subscription is None:
        return jsonify({"error": "Push subscription required"}), 400

    sub_json = json.dumps(push_subscription)
    endpoint = push_subscription.get("endpoint", "")

    with get_db() as conn:
        existing = conn.execute(
            "SELECT token FROM users WHERE push_subscription LIKE ? AND active=1",
            (f"%{endpoint}%",),
        ).fetchone()
        if existing:
            return jsonify({"token": existing["token"]})
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO users (token, area_url, target_date, push_subscription) VALUES (?,?,?,?)",
            (token, area_url, target_date, sub_json),
        )

    threading.Thread(
        target=_notify_existing_slots,
        args=(area_url, target_dt, sub_json),
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
    return jsonify({"area_name": area_name, "target_date": user["target_date"]})


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
            conn.execute("UPDATE users SET active=0 WHERE token=?", (token,))
            remaining = conn.execute(
                "SELECT COUNT(*) FROM users WHERE area_url=? AND active=1",
                (user["area_url"],),
            ).fetchone()[0]
            if remaining == 0:
                conn.execute(
                    "DELETE FROM active_slots WHERE url=?", (user["area_url"],)
                )
        return render_template("unsubscribe.html", done=True)

    return render_template(
        "unsubscribe.html",
        token=token,
        done=False,
        area_name=area_name,
        target_date=user["target_date"],
    )


def _notify_existing_slots(area_url: str, target_dt: datetime, sub_json: str) -> None:
    """Alert a newly registered user about slots that are already in the DB."""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT slot_date, slot_time, clinic FROM active_slots WHERE url=?",
                (area_url,),
            ).fetchall()
        for row in rows:
            slot_dt = datetime.strptime(row["slot_date"], "%Y-%m-%d")
            if slot_dt <= target_dt:
                body = f"{slot_dt.strftime('%d %b %Y')} at {row['slot_time']} — {row['clinic']}"
                send_push(sub_json, "SwiftQueue slot available!", body, area_url)
    except Exception:
        pass
