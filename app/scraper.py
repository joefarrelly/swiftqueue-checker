import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def fetch_slots(url: str) -> list[tuple[datetime, str, str, str]]:
    """Return all available slots as (date, time, clinic, booking_url) tuples."""
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results: list[tuple[datetime, str, str, str]] = []
    current_clinic = "Unknown clinic"
    last_time = ""
    last_booking_url = ""

    for tag in soup.find_all(["h3", "h4"]):
        if tag.name == "h3":
            text = tag.get_text(strip=True)
            if "Next available" not in text:
                current_clinic = text
                last_time = ""
                last_booking_url = ""
        elif tag.name == "h4":
            text = tag.get_text(strip=True)
            if _TIME_RE.match(text):
                last_time = text
                a = tag.find("a")
                if a and a.get("href"):
                    last_booking_url = urljoin(url, a["href"])
            else:
                try:
                    dt = datetime.strptime(text, "%d-%m-%Y")
                    results.append((dt, last_time, current_clinic, last_booking_url))
                    last_time = ""
                    last_booking_url = ""
                except ValueError:
                    pass

    return results
