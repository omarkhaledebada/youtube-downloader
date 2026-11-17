"""Data models describing a resolved YouTube playlist."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PlaylistEntry:
    index: int
    video_id: str
    title: str
    url: str
    duration_seconds: Optional[int]
    thumbnail_url: Optional[str]

    @property
    def duration_display(self) -> str:
        if not self.duration_seconds:
            return "--:--"
        seconds = int(self.duration_seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:d}:{secs:02d}"


@dataclass
class PlaylistInfo:
    playlist_id: str
    title: str
    uploader: Optional[str]
    entries: List[PlaylistEntry] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.entries)
