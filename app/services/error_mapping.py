"""Shared translation from raw yt-dlp/network exceptions into the
application's typed AppError subclasses, so both the analysis and the
download paths report errors identically."""
from __future__ import annotations

import yt_dlp

from app.services.exceptions import (
    ExtractionError,
    GeoRestrictedError,
    InvalidUrlError,
    NetworkError,
    PrivateVideoError,
    VideoRemovedError,
    VideoUnavailableError,
)


def classify_download_error(exc: BaseException) -> Exception:
    message = str(exc).lower()

    if "private video" in message:
        return PrivateVideoError()
    if "video unavailable" in message and "removed" in message:
        return VideoRemovedError()
    if "video unavailable" in message:
        return VideoUnavailableError()
    if ("not available in your country" in message) or ("geo" in message and "restrict" in message):
        return GeoRestrictedError()
    if any(
        term in message
        for term in ("urlopen error", "timed out", "connection", "network", "resolve host", "temporary failure")
    ):
        return NetworkError()
    if "unsupported url" in message or "is not a valid url" in message:
        return InvalidUrlError()

    return ExtractionError(str(exc))
