"""Input validation helpers for URLs and filesystem paths."""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse, parse_qs

_YOUTUBE_HOST_PATTERN = re.compile(
    r"^(www\.|m\.|music\.)?(youtube\.com|youtu\.be)$", re.IGNORECASE
)

_VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,}$")


def is_valid_youtube_url(url: str) -> bool:
    """Best-effort validation that a string looks like a YouTube video/shorts URL."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url:
        return False
    if not url.lower().startswith(("http://", "https://")):
        url = f"https://{url}"

    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if not parsed.netloc or not _YOUTUBE_HOST_PATTERN.match(parsed.netloc):
        return False

    if "youtu.be" in parsed.netloc.lower():
        video_id = parsed.path.strip("/").split("/")[0]
        return bool(video_id) and bool(_VIDEO_ID_PATTERN.match(video_id))

    path = parsed.path.lower()
    if path in ("/watch",):
        query = parse_qs(parsed.query)
        video_id = query.get("v", [""])[0]
        return bool(video_id) and bool(_VIDEO_ID_PATTERN.match(video_id))
    if path.startswith("/shorts/") or path.startswith("/live/") or path.startswith("/embed/"):
        video_id = path.split("/")[2] if len(path.split("/")) > 2 else ""
        return bool(video_id) and bool(_VIDEO_ID_PATTERN.match(video_id))

    return False


def normalize_youtube_url(url: str) -> str:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def extract_playlist_id(url: str) -> str | None:
    """Return the `list=` query parameter of a YouTube URL, if present."""
    if not url:
        return None
    try:
        parsed = urlparse(normalize_youtube_url(url))
    except ValueError:
        return None

    if not parsed.netloc or not _YOUTUBE_HOST_PATTERN.match(parsed.netloc):
        return None

    query = parse_qs(parsed.query)
    list_id = query.get("list", [None])[0]
    if not list_id:
        return None
    return list_id


def is_youtube_playlist_url(url: str) -> bool:
    """True when the URL references a playlist (with or without a specific
    video also selected, e.g. `watch?v=...&list=...`)."""
    return extract_playlist_id(url) is not None


def is_writable_directory(path: str) -> bool:
    """Check whether a directory exists (or can be created) and is writable."""
    if not path:
        return False
    try:
        os.makedirs(path, exist_ok=True)
        return os.access(path, os.W_OK)
    except OSError:
        return False
