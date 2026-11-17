"""Filename sanitization and collision-safe path generation for Windows."""
from __future__ import annotations

import os
import re

_INVALID_WINDOWS_CHARS = r'<>:"/\\|?*'
_INVALID_CHARS_PATTERN = re.compile(f"[{re.escape(_INVALID_WINDOWS_CHARS)}]")
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_BASENAME_LENGTH = 150  # keep headroom below the 255-char path component limit


def sanitize_filename(name: str, fallback: str = "download") -> str:
    """Strip characters that are illegal in Windows filenames and trim length."""
    if not name:
        name = fallback

    # Remove control characters and Windows-reserved characters.
    cleaned = _INVALID_CHARS_PATTERN.sub("_", name)
    cleaned = "".join(ch for ch in cleaned if ord(ch) >= 32)

    # Windows does not allow filenames to end with a space or a dot.
    cleaned = cleaned.strip().rstrip(".")
    cleaned = cleaned.strip()

    if not cleaned:
        cleaned = fallback

    if cleaned.upper() in _RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    if len(cleaned) > _MAX_BASENAME_LENGTH:
        cleaned = cleaned[:_MAX_BASENAME_LENGTH].rstrip()

    return cleaned


def unique_path(directory: str, filename: str) -> str:
    """Return a path in `directory` for `filename` that does not already exist,
    appending ' (1)', ' (2)', ... before the extension as needed."""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base} ({counter}){ext}")
        counter += 1
    return candidate
