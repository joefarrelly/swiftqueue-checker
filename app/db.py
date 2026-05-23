import sqlite3
from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "swiftqueue.db"


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                token             TEXT UNIQUE NOT NULL,
                area_url          TEXT NOT NULL,
                target_date       DATE NOT NULL,
                push_subscription TEXT,
                telegram_chat_id  TEXT,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active            INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS telegram_subscribers (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                token     TEXT NOT NULL,
                chat_id   TEXT NOT NULL,
                linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (token, chat_id)
            );

            CREATE TABLE IF NOT EXISTS telegram_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                token      TEXT NOT NULL,
                chat_id    TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                area_url   TEXT NOT NULL,
                slot_date  DATE NOT NULL,
                slot_time  TEXT NOT NULL,
                clinic     TEXT NOT NULL,
                UNIQUE (token, area_url, slot_date, slot_time, clinic)
            );

            CREATE TABLE IF NOT EXISTS area_meta (
                url            TEXT PRIMARY KEY,
                last_scraped_at TEXT
            );

            CREATE TABLE IF NOT EXISTS active_slots (
                url           TEXT NOT NULL,
                slot_date     DATE NOT NULL,
                slot_time     TEXT NOT NULL,
                clinic        TEXT NOT NULL,
                booking_url   TEXT DEFAULT '',
                first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                seen_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (url, slot_date, slot_time, clinic)
            );
        """)
        try:
            conn.execute(
                "ALTER TABLE active_slots ADD COLUMN booking_url TEXT DEFAULT ''"
            )
        except Exception:
            pass  # column already exists
