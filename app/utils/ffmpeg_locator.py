"""Locates an ffmpeg/ffprobe executable, whether bundled with the app,
sitting next to the executable, or available on the system PATH.
"""
from __future__ import annotations

import os
import shutil
import sys
from typing import Optional


def _app_base_dir() -> str:
    """Directory containing the running application (handles PyInstaller)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # main.py lives at the project root; app/utils/ffmpeg_locator.py -> up two levels
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _candidate_names(tool: str) -> list[str]:
    if sys.platform == "win32":
        return [f"{tool}.exe"]
    return [tool]


def find_executable(tool: str) -> Optional[str]:
    """Look for `tool` (e.g. 'ffmpeg') bundled next to the app, then on PATH."""
    base_dirs = []
    # PyInstaller (6+) unpacks bundled data into sys._MEIPASS (the "_internal"
    # folder), not next to the exe -- check there first.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base_dirs.append(meipass)
    base_dirs.append(_app_base_dir())

    search_dirs = []
    for base_dir in base_dirs:
        search_dirs += [
            os.path.join(base_dir, "ffmpeg", "bin"),
            os.path.join(base_dir, "ffmpeg"),
            base_dir,
        ]

    for directory in search_dirs:
        for name in _candidate_names(tool):
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

    on_path = shutil.which(tool)
    if on_path:
        return on_path

    return None


def find_ffmpeg() -> Optional[str]:
    return find_executable("ffmpeg")


def find_ffprobe() -> Optional[str]:
    return find_executable("ffprobe")


def get_ffmpeg_directory() -> Optional[str]:
    """Return the directory containing ffmpeg, for passing to yt-dlp's
    `ffmpeg_location` option (yt-dlp accepts either the binary or its dir)."""
    ffmpeg_path = find_ffmpeg()
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)
    return None
