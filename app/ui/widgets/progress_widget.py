"""Displays live download/merge progress: bar, percentage, sizes, speed, ETA."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from app.services.download_service import ProgressUpdate
from app.utils.formatting import format_bytes, format_eta, format_percent, format_speed


class ProgressWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._elapsed_seconds = 0
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._on_elapsed_tick)
        self._base_status_text = ""
        self._build_ui()
        self.reset()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.status_label = QLabel("")
        self.status_label.setObjectName("VideoTitleLabel")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        details_row = QHBoxLayout()
        self.size_label = QLabel("")
        self.size_label.setObjectName("VideoMetaLabel")
        details_row.addWidget(self.size_label)
        details_row.addStretch(1)

        self.percent_label = QLabel("")
        self.percent_label.setObjectName("VideoMetaLabel")
        details_row.addWidget(self.percent_label)
        layout.addLayout(details_row)

        stats_row = QHBoxLayout()
        self.speed_label = QLabel("")
        self.speed_label.setObjectName("VideoMetaLabel")
        stats_row.addWidget(self.speed_label)
        stats_row.addStretch(1)

        self.eta_label = QLabel("")
        self.eta_label.setObjectName("VideoMetaLabel")
        stats_row.addWidget(self.eta_label)
        layout.addLayout(stats_row)

    # Phases that don't report byte-level progress (FFmpeg merging/MP3
    # conversion, or the brief moment before the first byte arrives). For
    # these we switch to a busy/indeterminate bar and clear the leftover
    # download stats instead of leaving stale numbers on screen that no
    # longer mean anything (e.g. "144 MB / 144 MB" during a conversion that
    # has nothing to do with those bytes).
    _NO_BYTE_PROGRESS_PHASES = ("merging", "converting", "starting")

    def reset(self) -> None:
        self._stop_elapsed_timer()
        self.status_label.setText("")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.size_label.setText("")
        self.percent_label.setText("")
        self.speed_label.setText("")
        self.eta_label.setText("")

    def apply_update(self, update: ProgressUpdate) -> None:
        if update.phase in self._NO_BYTE_PROGRESS_PHASES:
            # Busy/indeterminate: QProgressBar shows a bouncing/marquee bar
            # (theme-dependent) when its range is (0, 0), which correctly
            # communicates "working, no known progress" instead of a
            # misleading stalled or leftover percentage. A ticking elapsed
            # counter next to the status text makes it visibly obvious this
            # is still alive rather than frozen -- these phases (fetching
            # fresh download links, running FFmpeg) can genuinely take a
            # few seconds with no byte-level progress to report.
            self._base_status_text = update.status_text
            self._start_elapsed_timer()
            self._update_status_with_elapsed()
            self.progress_bar.setRange(0, 0)
            self.percent_label.setText("")
            self.size_label.setText("")
            self.speed_label.setText("")
            self.eta_label.setText("")
            return

        self._stop_elapsed_timer()
        self.status_label.setText(update.status_text)
        self.progress_bar.setRange(0, 100)

        if update.percent is not None:
            self.progress_bar.setValue(int(max(0.0, min(1.0, update.percent)) * 100))
            self.percent_label.setText(format_percent(update.percent))

        if update.total_bytes:
            downloaded = format_bytes(update.downloaded_bytes)
            total = format_bytes(update.total_bytes)
            self.size_label.setText(f"{downloaded} / {total}")
        elif update.downloaded_bytes:
            self.size_label.setText(format_bytes(update.downloaded_bytes))
        else:
            self.size_label.setText("")

        self.speed_label.setText(
            f"Speed: {format_speed(update.speed_bytes_per_sec)}" if update.speed_bytes_per_sec else ""
        )
        self.eta_label.setText(
            f"ETA: {format_eta(update.eta_seconds)}" if update.eta_seconds is not None else ""
        )

    def _start_elapsed_timer(self) -> None:
        if not self._elapsed_timer.isActive():
            self._elapsed_seconds = 0
            self._elapsed_timer.start()

    def _stop_elapsed_timer(self) -> None:
        self._elapsed_timer.stop()
        self._elapsed_seconds = 0

    def _on_elapsed_tick(self) -> None:
        self._elapsed_seconds += 1
        self._update_status_with_elapsed()

    def _update_status_with_elapsed(self) -> None:
        if self._elapsed_seconds > 0:
            self.status_label.setText(f"{self._base_status_text} ({self._elapsed_seconds}s)")
        else:
            self.status_label.setText(self._base_status_text)
