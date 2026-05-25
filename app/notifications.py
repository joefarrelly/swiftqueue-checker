import json
import logging
import os

import requests

log = logging.getLogger(__name__)

_TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
_VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")


def send_telegram(chat_id: str, message: str) -> int | None:
    """Send a Telegram message. Returns message_id on success, None on failure."""
    if not _TELEGRAM_TOKEN:
        return None
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        if not r.ok:
            log.warning("Telegram error (%s): %s", chat_id, r.text)
            return None
        return r.json()["result"]["message_id"]
    except Exception as e:
        log.warning("Telegram send failed (%s): %s", chat_id, e)
        return None


def send_push(subscription_json: str, title: str, body: str, url: str) -> bool:
    """Send a push notification. Returns False if the subscription is gone and should be cleared."""
    if not _VAPID_PRIVATE_KEY or not subscription_json:
        return True
    try:
        from pywebpush import WebPushException, webpush

        webpush(
            subscription_info=json.loads(subscription_json),
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=_VAPID_PRIVATE_KEY,
            vapid_claims={"sub": "mailto:admin@queue4me.uk"},
        )
        return True
    except WebPushException as e:
        if e.response is not None and e.response.status_code == 410:
            return False
        log.warning("Push notification failed: %s", e)
        return True
    except Exception as e:
        log.warning("Push notification failed: %s", e)
        return True


def edit_telegram_message(chat_id: str, message_id: int, message: str) -> None:
    if not _TELEGRAM_TOKEN:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        if not r.ok:
            log.warning(
                "Telegram edit failed (%s, %s): %s", chat_id, message_id, r.text
            )
    except Exception as e:
        log.warning("Telegram edit error (%s): %s", chat_id, e)
