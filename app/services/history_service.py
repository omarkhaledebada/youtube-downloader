"""Download history persistence using SQLite (a single local file DB --
no server, no external dependency beyond the Python standard library)."""
from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

STATUS_DOWNLOADING = "Downloading"
STATUS_COMPLETED = "Completed"
STATUS_FAILED = "Failed"
STATUS_CANCELLED = "Cancelled"


@dataclass
class HistoryEntry:
    id: int
    title: str
    downloaded_at: str  # ISO 8601
    quality: str
    file_path: str
    status: str  # "Downloading" | "Completed" | "Failed" | "Cancelled"
    url: str = ""
    destination_dir: str = ""


def _db_directory() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        directory = os.path.join(base, "YouTubeDownloader")
    else:
        directory = os.path.join(os.path.expanduser("~"), ".youtube_downloader")
    os.makedirs(directory, exist_ok=True)
    return directory


class HistoryService:
    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or os.path.join(_db_directory(), "history.sqlite3")
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    downloaded_at TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            # Migrate older databases (created before `url` / `destination_dir`
            # existed) in place, so existing history isn't lost or reset.
            existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(history)")}
            if "url" not in existing_columns:
                conn.execute("ALTER TABLE history ADD COLUMN url TEXT NOT NULL DEFAULT ''")
            if "destination_dir" not in existing_columns:
                conn.execute("ALTER TABLE history ADD COLUMN destination_dir TEXT NOT NULL DEFAULT ''")
            conn.commit()

    def add_entry(
        self,
        title: str,
        quality: str,
        file_path: str,
        status: str,
        url: str = "",
        destination_dir: str = "",
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO history (title, downloaded_at, quality, file_path, status, url, destination_dir) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    title,
                    datetime.now().isoformat(timespec="seconds"),
                    quality,
                    file_path,
                    status,
                    url,
                    destination_dir,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def update_status(self, entry_id: int, status: str, file_path: Optional[str] = None) -> None:
        with self._connect() as conn:
            if file_path is not None:
                conn.execute(
                    "UPDATE history SET status = ?, file_path = ? WHERE id = ?",
                    (status, file_path, entry_id),
                )
            else:
                conn.execute("UPDATE history SET status = ? WHERE id = ?", (status, entry_id))
            conn.commit()

    def list_entries(self) -> List[HistoryEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, downloaded_at, quality, file_path, status, url, destination_dir "
                "FROM history ORDER BY id DESC"
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def list_incomplete(self) -> List[HistoryEntry]:
        """Entries still marked 'Downloading' -- these are downloads that
        were in progress when the app last closed (crash, forced close, or
        the user quitting mid-download), since a normal run always updates
        the status to Completed/Failed/Cancelled when a download ends."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, downloaded_at, quality, file_path, status, url, destination_dir "
                "FROM history WHERE status = ? ORDER BY id DESC",
                (STATUS_DOWNLOADING,),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> HistoryEntry:
        return HistoryEntry(
            id=row["id"],
            title=row["title"],
            downloaded_at=row["downloaded_at"],
            quality=row["quality"],
            file_path=row["file_path"],
            status=row["status"],
            url=row["url"] if "url" in row.keys() else "",
            destination_dir=row["destination_dir"] if "destination_dir" in row.keys() else "",
        )

    def remove_entry(self, entry_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM history WHERE id = ?", (entry_id,))
            conn.commit()

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM history")
            conn.commit()
