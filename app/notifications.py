import logging
import os

import requests

log = logging.getLogger(__name__)

_TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")


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
