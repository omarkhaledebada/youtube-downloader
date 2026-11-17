"""Batch/Queue download dialog: paste (or drag & drop) several different
YouTube links at once, pick one quality, and download them one after
another with a live per-item status list."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import SettingsManager
from app.models.format_option import StreamType
from app.services.batch_title_worker import BatchTitleController
from app.services.download_service import DownloadRequest
from app.services.format_processor import build_playlist_quality_choices
from app.services.history_service import HistoryService
from app.services.playlist_download_service import PlaylistDownloadController
from app.utils.validators import is_valid_youtube_url, is_writable_directory

_STATUS_PENDING = "Pending"
_STATUS_DOWNLOADING = "Downloading"
_STATUS_COMPLETED = "Completed"
_STATUS_FAILED = "Failed"


class BatchQueueDialog(QDialog):
    def __init__(
        self,
        settings_manager: SettingsManager,
        history_service: HistoryService,
        destination_dir: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager
        self._history_service = history_service
        self._destination_dir = destination_dir

        self.setWindowTitle("Batch Download (Queue)")
        self.setAcceptDrops(True)
        self.resize(560, 560)

        self._title_controller = BatchTitleController(self)
        self._queue_controller = PlaylistDownloadController(self)
        self._quality_choices = build_playlist_quality_choices()

        self._requests: List[DownloadRequest] = []
        self._history_ids: List[Optional[int]] = []

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        instructions = QLabel("Paste one YouTube link per line, or drag & drop links here:")
        instructions.setObjectName("VideoMetaLabel")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.urls_edit = QTextEdit()
        self.urls_edit.setPlaceholderText(
            "https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=...\n..."
        )
        self.urls_edit.setAcceptDrops(False)  # let the dialog itself handle drops
        self.urls_edit.setMinimumHeight(120)
        layout.addWidget(self.urls_edit)

        options_row = QHBoxLayout()
        options_row.addWidget(QLabel("Quality"))
        self.quality_combo = QComboBox()
        for choice in self._quality_choices:
            self.quality_combo.addItem(choice.label)
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        options_row.addWidget(self.quality_combo, 1)
        layout.addLayout(options_row)

        self.mp3_checkbox = QCheckBox("Convert audio to MP3")
        self.mp3_checkbox.setVisible(False)
        layout.addWidget(self.mp3_checkbox)

        self.status_list = QListWidget()
        self.status_list.setMinimumHeight(220)
        layout.addWidget(self.status_list)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("VideoMetaLabel")
        layout.addWidget(self.summary_label)

        buttons_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Queue")
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.clicked.connect(self._on_start_clicked)
        buttons_row.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("Cancel Queue")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        buttons_row.addWidget(self.cancel_btn)

        self.retry_failed_btn = QPushButton("Retry Failed")
        self.retry_failed_btn.setEnabled(False)
        self.retry_failed_btn.clicked.connect(self._on_retry_failed_clicked)
        buttons_row.addWidget(self.retry_failed_btn)

        buttons_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self._on_close_clicked)
        buttons_row.addWidget(close_btn)

        layout.addLayout(buttons_row)

    def _connect_signals(self) -> None:
        self._title_controller.finished.connect(self._on_titles_resolved)
        self._queue_controller.item_started.connect(self._on_item_started)
        self._queue_controller.item_progress.connect(self._on_item_progress)
        self._queue_controller.item_finished.connect(self._on_item_finished)
        self._queue_controller.item_failed.connect(self._on_item_failed)
        self._queue_controller.finished.connect(self._on_queue_finished)
        self._queue_controller.cancelled.connect(self._on_queue_cancelled)

    # ------------------------------------------------------------------
    # Drag & drop: dropping links anywhere on the dialog appends them.
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasText() or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        lines: List[str] = []
        if event.mimeData().hasUrls():
            lines = [url.toString() for url in event.mimeData().urls()]
        elif event.mimeData().hasText():
            lines = [line.strip() for line in event.mimeData().text().splitlines() if line.strip()]

        if lines:
            existing = self.urls_edit.toPlainText()
            separator = "\n" if existing and not existing.endswith("\n") else ""
            self.urls_edit.setPlainText(existing + separator + "\n".join(lines))
        event.acceptProposedAction()

    # ------------------------------------------------------------------
    def _on_quality_changed(self, index: int) -> None:
        quality = self._quality_choices[index] if 0 <= index < len(self._quality_choices) else None
        self.mp3_checkbox.setVisible(bool(quality and quality.stream_type == StreamType.AUDIO_ONLY))

    def _parse_urls(self) -> List[str]:
        raw_lines = self.urls_edit.toPlainText().splitlines()
        urls: List[str] = []
        seen = set()
        for line in raw_lines:
            url = line.strip()
            if not url or url in seen:
                continue
            if not is_valid_youtube_url(url):
                continue
            seen.add(url)
            urls.append(url)
        return urls

    def _on_start_clicked(self) -> None:
        urls = self._parse_urls()
        if not urls:
            QMessageBox.warning(
                self, "No Valid Links", "Please paste at least one valid YouTube video link."
            )
            return

        if not is_writable_directory(self._destination_dir):
            QMessageBox.warning(
                self, "Invalid Folder", "The default download folder is not writable. Check it in Settings."
            )
            return

        self.start_btn.setEnabled(False)
        self.urls_edit.setEnabled(False)
        self.quality_combo.setEnabled(False)
        self.status_list.clear()
        self.summary_label.setText(f"Resolving titles for {len(urls)} link(s)...")

        self._title_controller.resolve(urls)

    def _on_titles_resolved(self, results: list) -> None:
        quality = self._quality_choices[self.quality_combo.currentIndex()]
        convert_to_mp3 = self.mp3_checkbox.isChecked() and quality.stream_type == StreamType.AUDIO_ONLY
        bitrate_text = self._settings_manager.get_audio_quality()
        try:
            bitrate = int(bitrate_text.split()[0])
        except (ValueError, IndexError):
            bitrate = 192

        self._requests = [
            DownloadRequest(
                url=url,
                title=title,
                quality=quality,
                destination_dir=self._destination_dir,
                convert_to_mp3=convert_to_mp3,
                mp3_bitrate_kbps=bitrate,
            )
            for url, title in results
        ]
        self._history_ids = [None] * len(self._requests)

        self.status_list.clear()
        for request in self._requests:
            item = QListWidgetItem(f"{_STATUS_PENDING} — {request.title}")
            self.status_list.addItem(item)

        self.summary_label.setText("")
        self.cancel_btn.setEnabled(True)
        self._queue_controller.start(self._requests)

    def _on_item_started(self, position: int, total: int, title: str) -> None:
        index = position - 1
        if 0 <= index < self.status_list.count():
            self.status_list.item(index).setText(f"{_STATUS_DOWNLOADING} — {title}")
        request = self._requests[index]
        history_id = self._history_service.add_entry(
            request.title,
            request.quality.label,
            "",
            "Downloading",
            url=request.url,
            destination_dir=request.destination_dir,
        )
        self._history_ids[index] = history_id
        self.summary_label.setText(f"Downloading {position} of {total}...")

    def _on_item_progress(self, update) -> None:
        pass  # Per-item byte-level progress isn't surfaced in the compact list view.

    def _on_item_finished(self, position: int, file_path: str) -> None:
        index = position - 1
        request = self._requests[index]
        if 0 <= index < self.status_list.count():
            self.status_list.item(index).setText(f"{_STATUS_COMPLETED} — {request.title}")
        history_id = self._history_ids[index]
        if history_id is not None:
            self._history_service.update_status(history_id, "Completed", file_path)

    def _on_item_failed(self, position: int, message: str) -> None:
        index = position - 1
        request = self._requests[index]
        if 0 <= index < self.status_list.count():
            self.status_list.item(index).setText(f"{_STATUS_FAILED} — {request.title} ({message})")
        history_id = self._history_ids[index]
        if history_id is not None:
            self._history_service.update_status(history_id, "Failed")

    def _on_queue_finished(self, succeeded: int, failed: int) -> None:
        self.start_btn.setEnabled(True)
        self.urls_edit.setEnabled(True)
        self.quality_combo.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.retry_failed_btn.setEnabled(failed > 0)
        self.summary_label.setText(f"Done: {succeeded} succeeded, {failed} failed.")

    def _on_queue_cancelled(self) -> None:
        self.start_btn.setEnabled(True)
        self.urls_edit.setEnabled(True)
        self.quality_combo.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.summary_label.setText("Queue cancelled.")

    def _on_cancel_clicked(self) -> None:
        self.cancel_btn.setEnabled(False)
        self._queue_controller.cancel()

    def _on_retry_failed_clicked(self) -> None:
        failed_requests = []
        for index in range(self.status_list.count()):
            if self.status_list.item(index).text().startswith(_STATUS_FAILED):
                failed_requests.append(self._requests[index])

        if not failed_requests:
            return

        self._requests = failed_requests
        self._history_ids = [None] * len(self._requests)
        self.status_list.clear()
        for request in self._requests:
            self.status_list.addItem(QListWidgetItem(f"{_STATUS_PENDING} — {request.title}"))

        self.retry_failed_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.summary_label.setText("")
        self._queue_controller.start(self._requests)

    def _on_close_clicked(self) -> None:
        if self._queue_controller.is_running:
            reply = QMessageBox.question(
                self,
                "Queue In Progress",
                "The queue is still downloading. Cancel it and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._queue_controller.cancel()
        self.reject()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._queue_controller.is_running:
            self._queue_controller.cancel()
        super().closeEvent(event)
