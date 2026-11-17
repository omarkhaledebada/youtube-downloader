"""Availability checks for FFmpeg. Actual merging/converting is delegated
to yt-dlp's built-in postprocessors (which shell out to ffmpeg internally
using argument lists, never a raw shell string), so this service's job is
purely to detect FFmpeg up front and fail with a clear message instead of
a mid-download crash."""
from __future__ import annotations

from app.utils.ffmpeg_locator import find_ffmpeg


class FfmpegService:
    def is_available(self) -> bool:
        return find_ffmpeg() is not None

    def executable_path(self) -> str | None:
        return find_ffmpeg()
