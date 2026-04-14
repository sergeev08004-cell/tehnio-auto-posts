from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

from news_bot.models import CandidateItem
from news_bot.text_tools import normalize_url, title_key


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.db_path))
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS published_items (
                fingerprint TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                title TEXT NOT NULL,
                title_key TEXT NOT NULL,
                url TEXT NOT NULL,
                normalized_url TEXT NOT NULL,
                published_at TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                topic TEXT NOT NULL,
                score REAL NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS cycle_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def was_published(self, fingerprint: str) -> bool:
        cursor = self.connection.execute(
            "SELECT 1 FROM published_items WHERE fingerprint = ? LIMIT 1",
            (fingerprint,)
        )
        return cursor.fetchone() is not None

    def mark_published(self, item: CandidateItem) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """
            INSERT OR REPLACE INTO published_items (
                fingerprint, source_name, title, title_key, url, normalized_url, published_at, sent_at, topic, score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.fingerprint,
                item.source_name,
                item.title,
                title_key(item.title),
                item.url,
                normalize_url(item.url),
                item.published_at_utc.isoformat(),
                now,
                item.topic,
                item.score
            )
        )
        self.connection.execute(
            "INSERT INTO cycle_events (event_type, value, created_at) VALUES (?, ?, ?)",
            ("publish", item.fingerprint, now)
        )
        self.connection.commit()

    def looks_like_published(self, item_title_key: str, item_url: str) -> bool:
        normalized = normalize_url(item_url)
        cursor = self.connection.execute(
            """
            SELECT title_key, normalized_url
            FROM published_items
            ORDER BY sent_at DESC
            LIMIT 250
            """
        )
        for row in cursor.fetchall():
            if row["normalized_url"] == normalized:
                return True

            similarity = SequenceMatcher(None, row["title_key"], item_title_key).ratio()
            if similarity >= 0.92:
                return True

        return False

    def can_publish_now(self, min_gap_minutes: int) -> bool:
        if min_gap_minutes <= 0:
            return True

        cursor = self.connection.execute(
            """
            SELECT sent_at
            FROM published_items
            ORDER BY sent_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row is None:
            return True

        sent_at = datetime.fromisoformat(row["sent_at"]).astimezone(timezone.utc)
        return datetime.now(timezone.utc) - sent_at >= timedelta(minutes=min_gap_minutes)
