"""Data model describing a resolved YouTube video, independent of yt-dlp's
raw dictionary shape so the rest of the app never touches raw yt-dlp data."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.models.format_option import FormatOption


@dataclass
class VideoInfo:
    video_id: str
    title: str
    channel: str
    duration_seconds: int
    thumbnail_url: Optional[str]
    upload_date: Optional[str]  # YYYYMMDD as provided by yt-dlp
    view_count: Optional[int]
    webpage_url: str
    formats: List[FormatOption] = field(default_factory=list)
    raw_formats: List[dict] = field(default_factory=list)

    @property
    def duration_display(self) -> str:
        return _format_duration(self.duration_seconds)

    @property
    def upload_date_display(self) -> Optional[str]:
        if not self.upload_date or len(self.upload_date) != 8:
            return None
        year, month, day = self.upload_date[:4], self.upload_date[4:6], self.upload_date[6:8]
        return f"{year}-{month}-{day}"

    @property
    def view_count_display(self) -> Optional[str]:
        if self.view_count is None:
            return None
        if self.view_count >= 1_000_000:
            return f"{self.view_count / 1_000_000:.1f}M views"
        if self.view_count >= 1_000:
            return f"{self.view_count / 1_000:.1f}K views"
        return f"{self.view_count} views"


def _format_duration(seconds: int) -> str:
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"
