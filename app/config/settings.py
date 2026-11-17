"""
Application settings persistence built on top of QSettings.

All user-configurable preferences (download folder, default quality,
window geometry, theme, etc.) go through this single class so the rest
of the application never touches QSettings directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QSettings, QByteArray

ORG_NAME = "HRKLIX"
APP_NAME = "YouTubeDownloader"

DEFAULT_QUALITY_OPTIONS = ["Best", "2160p", "1440p", "1080p", "720p"]
DEFAULT_FORMAT_OPTIONS = ["MP4", "Best Available"]
DEFAULT_AUDIO_QUALITY_OPTIONS = ["128 kbps", "192 kbps", "256 kbps", "320 kbps"]
THEME_OPTIONS = ["Light", "Dark", "System"]


def _default_download_dir() -> str:
    """Return a sensible default download directory (Downloads/YouTube)."""
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads", "YouTube")
    return downloads


@dataclass
class AppSettings:
    """In-memory snapshot of persisted settings, backed by QSettings."""

    download_folder: str
    default_quality: str
    default_format: str
    audio_quality: str
    auto_open_folder: bool
    remember_window_position: bool
    theme: str
    window_geometry: Optional[bytes] = None


class SettingsManager:
    """Thin, typed wrapper around QSettings for this application."""

    def __init__(self) -> None:
        self._settings = QSettings(ORG_NAME, APP_NAME)

    # ---- Download folder -------------------------------------------------
    def get_download_folder(self) -> str:
        value = self._settings.value("paths/download_folder", "", str)
        if not value:
            value = _default_download_dir()
            self.set_download_folder(value)
        return value

    def set_download_folder(self, path: str) -> None:
        self._settings.setValue("paths/download_folder", path)

    # ---- Default quality / format -----------------------------------------
    def get_default_quality(self) -> str:
        return self._settings.value("download/default_quality", "Best", str)

    def set_default_quality(self, quality: str) -> None:
        self._settings.setValue("download/default_quality", quality)

    def get_default_format(self) -> str:
        return self._settings.value("download/default_format", "MP4", str)

    def set_default_format(self, fmt: str) -> None:
        self._settings.setValue("download/default_format", fmt)

    def get_audio_quality(self) -> str:
        return self._settings.value("download/audio_quality", "192 kbps", str)

    def set_audio_quality(self, quality: str) -> None:
        self._settings.setValue("download/audio_quality", quality)

    # ---- Behaviour toggles --------------------------------------------------
    def get_auto_open_folder(self) -> bool:
        return self._settings.value("behaviour/auto_open_folder", False, bool)

    def set_auto_open_folder(self, value: bool) -> None:
        self._settings.setValue("behaviour/auto_open_folder", value)

    def get_remember_window_position(self) -> bool:
        return self._settings.value("behaviour/remember_window_position", True, bool)

    def set_remember_window_position(self, value: bool) -> None:
        self._settings.setValue("behaviour/remember_window_position", value)

    # ---- Theme ---------------------------------------------------------------
    def get_theme(self) -> str:
        return self._settings.value("appearance/theme", "System", str)

    def set_theme(self, theme: str) -> None:
        self._settings.setValue("appearance/theme", theme)

    # ---- Window geometry -------------------------------------------------------
    def get_window_geometry(self) -> Optional[QByteArray]:
        value = self._settings.value("window/geometry", None)
        return value

    def set_window_geometry(self, geometry: QByteArray) -> None:
        self._settings.setValue("window/geometry", geometry)

    # ---- Convenience -----------------------------------------------------------
    def snapshot(self) -> AppSettings:
        return AppSettings(
            download_folder=self.get_download_folder(),
            default_quality=self.get_default_quality(),
            default_format=self.get_default_format(),
            audio_quality=self.get_audio_quality(),
            auto_open_folder=self.get_auto_open_folder(),
            remember_window_position=self.get_remember_window_position(),
            theme=self.get_theme(),
        )

    def sync(self) -> None:
        self._settings.sync()
