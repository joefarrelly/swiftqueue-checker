import json
import logging
import os

import requests
from pywebpush import WebPushException, webpush

log = logging.getLogger(__name__)

_VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
_VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "")
_TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")


def send_push(subscription_json: str, title: str, body: str, url: str) -> None:
    if not _VAPID_PRIVATE_KEY:
        log.warning("VAPID_PRIVATE_KEY not set — skipping push notification")
        return
    try:
        webpush(
            subscription_info=json.loads(subscription_json),
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=_VAPID_PRIVATE_KEY,
            vapid_claims={"sub": _VAPID_CLAIMS_EMAIL},
        )
    except WebPushException as e:
        log.warning("Push failed: %s", e)
    except Exception as e:
        log.warning("Push error: %s", e)


def send_telegram(chat_id: str, message: str) -> None:
    if not _TELEGRAM_TOKEN:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        if not r.ok:
            log.warning("Telegram error (%s): %s", chat_id, r.text)
    except Exception as e:
        log.warning("Telegram send failed (%s): %s", chat_id, e)
