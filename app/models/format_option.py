"""Data models describing selectable download options."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class StreamType(Enum):
    VIDEO_AND_AUDIO = "Video + Audio"
    VIDEO_ONLY = "Video Only"
    AUDIO_ONLY = "Audio Only"


@dataclass
class FormatOption:
    """A single raw yt-dlp format, normalized to typed fields."""

    format_id: str
    ext: str
    resolution: Optional[str]  # "1920x1080"
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    vcodec: Optional[str]
    acodec: Optional[str]
    filesize: Optional[int]  # exact bytes, if known
    filesize_approx: Optional[int]  # approximate bytes, if known
    tbr: Optional[float]  # total average bitrate, kbps - used to estimate size
    abr: Optional[float]  # audio bitrate, kbps
    vbr: Optional[float]  # video bitrate, kbps
    format_note: Optional[str]
    protocol: Optional[str]

    @property
    def has_video(self) -> bool:
        return bool(self.vcodec) and self.vcodec != "none"

    @property
    def has_audio(self) -> bool:
        return bool(self.acodec) and self.acodec != "none"

    @property
    def stream_type(self) -> StreamType:
        if self.has_video and self.has_audio:
            return StreamType.VIDEO_AND_AUDIO
        if self.has_video:
            return StreamType.VIDEO_ONLY
        return StreamType.AUDIO_ONLY

    @property
    def best_known_size(self) -> Optional[int]:
        """Best size estimate available directly on this format, in bytes."""
        if self.filesize:
            return self.filesize
        if self.filesize_approx:
            return self.filesize_approx
        return None

    def estimate_size_from_bitrate(self, duration_seconds: Optional[int]) -> Optional[int]:
        """Fall back to bitrate * duration when YouTube doesn't hand us a
        filesize at all (common for many DASH video-only/audio-only
        formats, where neither `filesize` nor `filesize_approx` is set).

        This is the same math yt-dlp itself uses to fill in
        `filesize_approx` when it can -- multiplying the average bitrate by
        the duration -- so it's only used here as a genuine last resort,
        and the caller must still mark it as approximate.
        """
        if not duration_seconds or duration_seconds <= 0:
            return None

        bitrate_kbps = self.tbr
        if not bitrate_kbps:
            # tbr absent: combine video + audio bitrate if either is known.
            bitrate_kbps = (self.vbr or 0) + (self.abr or 0)

        if not bitrate_kbps:
            return None

        # kbps -> bytes/sec is *1000/8; multiplied by duration in seconds.
        return int(bitrate_kbps * 1000 / 8 * duration_seconds)

    @property
    def height_bucket(self) -> Optional[int]:
        """Rounds the height to a familiar quality bucket (2160/1440/1080/...)."""
        if not self.height:
            return None
        buckets = [144, 240, 360, 480, 720, 1080, 1440, 2160, 4320]
        closest = min(buckets, key=lambda b: abs(b - self.height))
        return closest


@dataclass
class QualityChoice:
    """A simplified, user-facing download choice.

    May be backed by a single muxed format (video+audio already combined)
    or by a pair of separate video-only + audio-only formats that will be
    merged with FFmpeg after downloading.
    """

    label: str  # "1080p", "Best Quality", "Audio Only", etc.
    resolution: Optional[str]
    fps: Optional[float]
    container: str  # "MP4", "WebM", "M4A" ...
    stream_type: StreamType
    estimated_size_bytes: Optional[int]
    size_is_approximate: bool
    video_format: Optional[FormatOption]
    audio_format: Optional[FormatOption]
    requires_merge: bool
    is_best_quality: bool = False
    is_audio_only: bool = False
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    sort_key: float = 0.0
    # For playlist downloads we don't analyze every video's raw formats up
    # front (too slow for large playlists); instead we build a generic
    # yt-dlp selector expression like "bestvideo[height<=1080]+bestaudio"
    # that is resolved fresh for each video at download time.
    raw_selector: Optional[str] = None

    @property
    def format_selector(self) -> str:
        """Build the yt-dlp format selection string for this choice."""
        if self.raw_selector:
            return self.raw_selector
        if self.video_format and self.audio_format:
            return f"{self.video_format.format_id}+{self.audio_format.format_id}"
        if self.video_format:
            return self.video_format.format_id
        if self.audio_format:
            return self.audio_format.format_id
        return "best"
