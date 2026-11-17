"""The application's single main window: URL entry, analysis results,
quality selection, download location, progress, and completion actions."""
from __future__ import annotations

import os
import sys
from typing import List, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QClipboard, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import SettingsManager
from app.models.format_option import StreamType
from app.models.playlist_info import PlaylistInfo
from app.models.video_info import VideoInfo
from app.services.analysis_worker import AnalysisController
from app.services.batch_title_worker import BatchTitleController
from app.services.download_service import DownloadController, DownloadRequest
from app.services.format_processor import build_quality_choices, get_generic_quality_by_label
from app.services.history_service import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_DOWNLOADING,
    STATUS_FAILED,
    HistoryService,
)
from app.services.playlist_analysis_worker import PlaylistAnalysisController
from app.services.playlist_download_service import PlaylistDownloadController
from app.ui.batch_queue_dialog import BatchQueueDialog
from app.ui.history_dialog import HistoryDialog
from app.ui.settings_dialog import SettingsDialog
from app.ui.styles import apply_theme, resolve_effective_theme
from app.ui.widgets.playlist_panel import PlaylistPanel
from app.ui.widgets.progress_widget import ProgressWidget
from app.ui.widgets.quality_list_widget import QualityListWidget
from app.ui.widgets.video_info_widget import VideoInfoWidget
from app.utils.logger import get_logger
from app.utils.validators import is_valid_youtube_url, is_writable_directory, is_youtube_playlist_url

logger = get_logger()

_CLIPBOARD_POLL_INTERVAL_MS = 1500

_PAGE_IDLE = 0
_PAGE_DOWNLOADING = 1
_PAGE_COMPLETE = 2


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._settings_manager = SettingsManager()
        self._history_service = HistoryService()
        self._analysis_controller = AnalysisController(self)
        self._download_controller = DownloadController(self)
        self._playlist_analysis_controller = PlaylistAnalysisController(self)
        self._playlist_download_controller = PlaylistDownloadController(self)
        self._retry_title_controller = BatchTitleController(self)

        self._current_video: Optional[VideoInfo] = None
        self._current_playlist: Optional[PlaylistInfo] = None
        self._is_playlist_mode = False
        self._download_folder = self._settings_manager.get_download_folder()
        self._last_finished_path: Optional[str] = None

        # Single-download History bookkeeping (so Retry/Resume can work).
        self._current_history_id: Optional[int] = None

        # Playlist/queue History bookkeeping, keyed by item position (1-based).
        self._playlist_history_ids: List[Optional[int]] = []

        # Resume-on-startup state: while resuming, the playlist download
        # controller is reused but item completion must update existing
        # history rows instead of creating new ones.
        self._is_resume_mode = False
        self._resume_history_ids: List[int] = []

        self._pending_retry_url: Optional[str] = None
        self._pending_retry_quality_label: Optional[str] = None

        self._clipboard_last_seen = ""
        self._clipboard_dismissed_text = ""

        self.setWindowTitle("YouTube Downloader")
        self.resize(760, 720)
        self.setMinimumSize(640, 560)
        self.setAcceptDrops(True)

        self._build_ui()
        self._connect_signals()
        self._restore_window_geometry()

        self._start_clipboard_watcher()
        QTimer.singleShot(300, self._check_resume_incomplete_downloads)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(20, 16, 20, 20)
        outer_layout.setSpacing(14)

        outer_layout.addLayout(self._build_header())

        self.clipboard_banner = self._build_clipboard_banner()
        self.clipboard_banner.setVisible(False)
        outer_layout.addWidget(self.clipboard_banner)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer_layout.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(14)
        content_layout.setContentsMargins(0, 0, 4, 0)

        content_layout.addWidget(self._build_url_card())

        self.video_info_widget = VideoInfoWidget()
        content_layout.addWidget(self._wrap_card(self.video_info_widget))
        self._video_info_card = self.video_info_widget.parentWidget()
        self._video_info_card.setVisible(False)

        self._quality_card = self._build_quality_card()
        content_layout.addWidget(self._quality_card)
        self._quality_card.setVisible(False)

        self.playlist_panel = PlaylistPanel()
        content_layout.addWidget(self._wrap_card(self.playlist_panel))
        self._playlist_card = self.playlist_panel.parentWidget()
        self._playlist_card.setVisible(False)

        content_layout.addWidget(self._build_destination_card())

        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_idle_page())
        self._pages.addWidget(self._build_downloading_page())
        self._pages.addWidget(self._build_complete_page())
        content_layout.addWidget(self._pages)

        content_layout.addStretch(1)

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        title = QLabel("YouTube Downloader")
        title.setObjectName("TitleLabel")
        layout.addWidget(title)
        layout.addStretch(1)

        self.theme_toggle_btn = QPushButton()
        self.theme_toggle_btn.setObjectName("IconButton")
        self.theme_toggle_btn.setToolTip("Toggle light / dark theme")
        self.theme_toggle_btn.clicked.connect(self._on_toggle_theme_clicked)
        self._update_theme_toggle_icon()
        layout.addWidget(self.theme_toggle_btn)

        batch_btn = QPushButton("Batch / Queue")
        batch_btn.clicked.connect(self._open_batch_queue)
        layout.addWidget(batch_btn)

        history_btn = QPushButton("History")
        history_btn.clicked.connect(self._open_history)
        layout.addWidget(history_btn)

        settings_btn = QPushButton("⚙  Settings")
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)
        return layout

    def _build_clipboard_banner(self) -> QWidget:
        card = QFrame()
        card.setObjectName("SurfaceCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        self.clipboard_banner_label = QLabel("A YouTube link was detected in your clipboard.")
        self.clipboard_banner_label.setWordWrap(True)
        layout.addWidget(self.clipboard_banner_label, 1)

        use_btn = QPushButton("Use Link")
        use_btn.setObjectName("PrimaryButton")
        use_btn.clicked.connect(self._on_use_clipboard_link)
        layout.addWidget(use_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.clicked.connect(self._on_dismiss_clipboard_banner)
        layout.addWidget(dismiss_btn)

        return card

    def _wrap_card(self, widget: QWidget) -> QWidget:
        card = QFrame()
        card.setObjectName("SurfaceCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(widget)
        return card

    def _build_url_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("SurfaceCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        label = QLabel("YouTube URL")
        label.setObjectName("SectionHeader")
        layout.addWidget(label)

        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_edit.returnPressed.connect(self._on_analyze_clicked)
        url_row.addWidget(self.url_edit, 1)

        paste_btn = QPushButton("Paste")
        paste_btn.clicked.connect(self._on_paste_clicked)
        url_row.addWidget(paste_btn)
        layout.addLayout(url_row)

        self.analyze_btn = QPushButton("Analyze Video")
        self.analyze_btn.setObjectName("PrimaryButton")
        self.analyze_btn.clicked.connect(self._on_analyze_clicked)
        layout.addWidget(self.analyze_btn)

        self.analyze_status_label = QLabel("")
        self.analyze_status_label.setObjectName("VideoMetaLabel")
        self.analyze_status_label.setWordWrap(True)
        layout.addWidget(self.analyze_status_label)

        return card

    def _build_quality_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("SurfaceCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        label = QLabel("Download Quality")
        label.setObjectName("SectionHeader")
        layout.addWidget(label)

        self.quality_list = QualityListWidget()
        layout.addWidget(self.quality_list)

        mp3_row = QHBoxLayout()
        self.mp3_checkbox = QCheckBox("Convert audio to MP3")
        mp3_row.addWidget(self.mp3_checkbox)
        mp3_row.addStretch(1)
        layout.addLayout(mp3_row)

        return card

    def _build_destination_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("SurfaceCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        label = QLabel("Save To")
        label.setObjectName("SectionHeader")
        layout.addWidget(label)

        row = QHBoxLayout()
        self.folder_label = QLabel(self._download_folder)
        self.folder_label.setWordWrap(True)
        row.addWidget(self.folder_label, 1)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._on_browse_folder)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        self.use_as_default_checkbox = QCheckBox("Use as default download folder")
        self.use_as_default_checkbox.setVisible(False)
        layout.addWidget(self.use_as_default_checkbox)

        return card

    def _build_idle_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        self.download_btn = QPushButton("Download")
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.setMinimumHeight(44)
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._on_download_clicked)
        layout.addWidget(self.download_btn)
        return page

    def _build_downloading_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("SurfaceCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(6)

        self.playlist_item_label = QLabel("")
        self.playlist_item_label.setObjectName("SectionHeader")
        self.playlist_item_label.setVisible(False)
        card_layout.addWidget(self.playlist_item_label)

        self.progress_widget = ProgressWidget()
        card_layout.addWidget(self.progress_widget)
        layout.addWidget(card)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self.cancel_btn)

        return page

    def _build_complete_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("SurfaceCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)

        self.complete_label = QLabel("Download completed successfully")
        self.complete_label.setObjectName("VideoTitleLabel")
        card_layout.addWidget(self.complete_label)
        layout.addWidget(card)

        buttons_row = QHBoxLayout()
        self.open_file_btn = QPushButton("Open File")
        self.open_file_btn.clicked.connect(self._open_finished_file)
        buttons_row.addWidget(self.open_file_btn)

        open_folder_btn = QPushButton("Open Folder")
        open_folder_btn.clicked.connect(self._open_finished_folder)
        buttons_row.addWidget(open_folder_btn)
        layout.addLayout(buttons_row)

        another_btn = QPushButton("Download Another")
        another_btn.setObjectName("PrimaryButton")
        another_btn.clicked.connect(self._on_download_another)
        layout.addWidget(another_btn)

        return page

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        self._analysis_controller.succeeded.connect(self._on_analysis_succeeded)
        self._analysis_controller.failed.connect(self._on_analysis_failed)

        self._download_controller.progress.connect(self._on_download_progress)
        self._download_controller.finished.connect(self._on_download_finished)
        self._download_controller.failed.connect(self._on_download_failed)
        self._download_controller.cancelled.connect(self._on_download_cancelled)

        self._playlist_analysis_controller.succeeded.connect(self._on_playlist_analysis_succeeded)
        self._playlist_analysis_controller.failed.connect(self._on_playlist_analysis_failed)

        self._playlist_download_controller.item_started.connect(self._on_playlist_item_started)
        self._playlist_download_controller.item_progress.connect(self._on_download_progress)
        self._playlist_download_controller.item_finished.connect(self._on_playlist_item_finished)
        self._playlist_download_controller.item_failed.connect(self._on_playlist_item_failed)
        self._playlist_download_controller.finished.connect(self._on_playlist_finished)
        self._playlist_download_controller.cancelled.connect(self._on_download_cancelled)

        self._retry_title_controller.finished.connect(self._on_retry_title_resolved)

        self.quality_list.selection_changed.connect(self._on_quality_selection_changed)

    # ------------------------------------------------------------------
    # Drag & drop: dropping a link anywhere on the window fills the URL box.
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        text = ""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                text = urls[0].toString()
        elif event.mimeData().hasText():
            text = event.mimeData().text().strip().splitlines()[0] if event.mimeData().text().strip() else ""

        if text:
            self.url_edit.setText(text.strip())
        event.acceptProposedAction()

    # ------------------------------------------------------------------
    # Clipboard auto-detect banner
    # ------------------------------------------------------------------
    def _start_clipboard_watcher(self) -> None:
        clipboard: QClipboard = QGuiApplication.clipboard()
        try:
            self._clipboard_last_seen = clipboard.text().strip()
        except Exception:  # noqa: BLE001
            self._clipboard_last_seen = ""

        self._clipboard_timer = QTimer(self)
        self._clipboard_timer.setInterval(_CLIPBOARD_POLL_INTERVAL_MS)
        self._clipboard_timer.timeout.connect(self._check_clipboard_for_link)
        self._clipboard_timer.start()

    def _check_clipboard_for_link(self) -> None:
        if not self.isActiveWindow():
            return
        try:
            text = QGuiApplication.clipboard().text().strip()
        except Exception:  # noqa: BLE001
            return

        if not text or text == self._clipboard_last_seen:
            return
        self._clipboard_last_seen = text

        if text == self._clipboard_dismissed_text:
            return
        if text == self.url_edit.text().strip():
            return
        if not (is_valid_youtube_url(text) or is_youtube_playlist_url(text)):
            return

        self._pending_clipboard_text = text
        self.clipboard_banner_label.setText(
            "A YouTube link was detected in your clipboard — use it?"
        )
        self.clipboard_banner.setVisible(True)

    def _on_use_clipboard_link(self) -> None:
        text = getattr(self, "_pending_clipboard_text", "")
        if text:
            self.url_edit.setText(text)
        self.clipboard_banner.setVisible(False)

    def _on_dismiss_clipboard_banner(self) -> None:
        self._clipboard_dismissed_text = getattr(self, "_pending_clipboard_text", "")
        self.clipboard_banner.setVisible(False)

    # ------------------------------------------------------------------
    # Theme toggle
    # ------------------------------------------------------------------
    def _update_theme_toggle_icon(self) -> None:
        theme = self._settings_manager.get_theme()
        app = QApplication.instance()
        effective = resolve_effective_theme(app, theme) if app else theme
        self.theme_toggle_btn.setText("☀  Light" if effective == "Dark" else "🌙  Dark")

    def _on_toggle_theme_clicked(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        current_effective = resolve_effective_theme(app, self._settings_manager.get_theme())
        new_theme = "Light" if current_effective == "Dark" else "Dark"
        self._settings_manager.set_theme(new_theme)
        self._settings_manager.sync()
        apply_theme(app, new_theme)
        self._update_theme_toggle_icon()

    # ------------------------------------------------------------------
    # Batch / Queue dialog
    # ------------------------------------------------------------------
    def _open_batch_queue(self) -> None:
        dialog = BatchQueueDialog(self._settings_manager, self._history_service, self._download_folder, self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Resume incomplete downloads on startup
    # ------------------------------------------------------------------
    def _check_resume_incomplete_downloads(self) -> None:
        incomplete = [entry for entry in self._history_service.list_incomplete() if entry.url]
        if not incomplete:
            return

        reply = QMessageBox.question(
            self,
            "Resume Downloads",
            f"{len(incomplete)} download(s) were interrupted last time the app was open. "
            "Resume them now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            for entry in incomplete:
                self._history_service.update_status(entry.id, STATUS_CANCELLED)
            return

        requests: List[DownloadRequest] = []
        ids: List[int] = []
        for entry in incomplete:
            quality = get_generic_quality_by_label(entry.quality) or get_generic_quality_by_label("Best Quality")
            requests.append(
                DownloadRequest(
                    url=entry.url,
                    title=entry.title or entry.url,
                    quality=quality,
                    destination_dir=entry.destination_dir or self._download_folder,
                    convert_to_mp3=False,
                    mp3_bitrate_kbps=192,
                )
            )
            ids.append(entry.id)

        if not requests:
            return

        self._is_resume_mode = True
        self._resume_history_ids = ids
        self.progress_widget.reset()
        self.playlist_item_label.setVisible(True)
        self.open_file_btn.setVisible(False)
        self._pages.setCurrentIndex(_PAGE_DOWNLOADING)
        self._playlist_download_controller.start(requests)

    # ------------------------------------------------------------------
    # Retry from History
    # ------------------------------------------------------------------
    def _on_retry_requested(self, url: str, quality_label: str) -> None:
        if self._download_controller.is_running or self._playlist_download_controller.is_running:
            QMessageBox.warning(self, "Busy", "Please wait for the current download to finish before retrying.")
            return

        quality = get_generic_quality_by_label(quality_label) or get_generic_quality_by_label("Best Quality")
        if quality is None:
            QMessageBox.warning(self, "Cannot Retry", "Could not determine a quality to retry with.")
            return

        self._pending_retry_url = url
        self._pending_retry_quality_label = quality_label

        if self._retry_title_controller.is_running:
            return
        self._retry_title_controller.resolve([url])

    def _on_retry_title_resolved(self, results: list) -> None:
        if not results or self._pending_retry_url is None:
            return
        url, title = results[0]
        quality = get_generic_quality_by_label(self._pending_retry_quality_label or "") or get_generic_quality_by_label(
            "Best Quality"
        )
        self._pending_retry_url = None
        self._pending_retry_quality_label = None

        if not is_writable_directory(self._download_folder):
            QMessageBox.warning(
                self, "Invalid Folder", "The default download folder is not writable. Check it in Settings."
            )
            return

        bitrate_text = self._settings_manager.get_audio_quality()
        try:
            bitrate = int(bitrate_text.split()[0])
        except (ValueError, IndexError):
            bitrate = 192

        request = DownloadRequest(
            url=url,
            title=title,
            quality=quality,
            destination_dir=self._download_folder,
            convert_to_mp3=quality.stream_type == StreamType.AUDIO_ONLY,
            mp3_bitrate_kbps=bitrate,
        )

        self._is_playlist_mode = False
        self._current_video = None
        self._current_history_id = self._history_service.add_entry(
            request.title,
            request.quality.label,
            "",
            STATUS_DOWNLOADING,
            url=request.url,
            destination_dir=request.destination_dir,
        )

        self.progress_widget.reset()
        self.playlist_item_label.setVisible(False)
        self.open_file_btn.setVisible(True)
        self._pages.setCurrentIndex(_PAGE_DOWNLOADING)
        self._download_controller.start(request)

    # ------------------------------------------------------------------
    # URL analysis
    # ------------------------------------------------------------------
    def _on_paste_clicked(self) -> None:
        clipboard: QClipboard = QGuiApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.url_edit.setText(text)

    def _on_analyze_clicked(self) -> None:
        url = self.url_edit.text().strip()

        if is_youtube_playlist_url(url):
            reply = QMessageBox.question(
                self,
                "Playlist Detected",
                "This URL is part of a playlist. Do you want to download the whole playlist "
                "or just this one video?",
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            # Yes -> whole playlist, No -> just the single video.
            if reply == QMessageBox.StandardButton.Yes:
                self._start_playlist_analysis(url)
                return

        if not is_valid_youtube_url(url):
            self.analyze_status_label.setText("The URL does not appear to be a valid YouTube video URL.")
            return

        if self._analysis_controller.is_running:
            return

        self._is_playlist_mode = False
        self._current_playlist = None
        self._playlist_card.setVisible(False)
        self.download_btn.setText("Download")

        self.analyze_status_label.setText("Analyzing video...")
        self.analyze_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        self._quality_card.setVisible(False)
        self._video_info_card.setVisible(False)

        self._analysis_controller.analyze(url)

    def _start_playlist_analysis(self, url: str) -> None:
        if self._playlist_analysis_controller.is_running:
            return

        self._is_playlist_mode = True
        self._current_video = None
        self._video_info_card.setVisible(False)
        self._quality_card.setVisible(False)
        self._playlist_card.setVisible(False)

        self.analyze_status_label.setText("Analyzing playlist...")
        self.analyze_btn.setEnabled(False)
        self.download_btn.setEnabled(False)

        self._playlist_analysis_controller.analyze(url)

    def _on_playlist_analysis_succeeded(self, playlist: PlaylistInfo) -> None:
        self.analyze_btn.setEnabled(True)
        self.analyze_status_label.setText("")
        self._current_playlist = playlist

        self.playlist_panel.display(playlist)
        self._playlist_card.setVisible(True)
        self.download_btn.setText("Download Playlist")
        self.download_btn.setEnabled(True)

    def _on_playlist_analysis_failed(self, message: str) -> None:
        self.analyze_btn.setEnabled(True)
        self.analyze_status_label.setText(message)
        self._current_playlist = None
        self._is_playlist_mode = False

    def _on_analysis_succeeded(self, video: VideoInfo) -> None:
        self.analyze_btn.setEnabled(True)
        self.analyze_status_label.setText("")
        self._current_video = video

        self.video_info_widget.display(video)
        self._video_info_card.setVisible(True)

        choices = build_quality_choices(video.formats, video.duration_seconds)
        if not choices:
            self.analyze_status_label.setText("No downloadable formats were found for this video.")
            self._quality_card.setVisible(False)
            self.download_btn.setEnabled(False)
            return

        self.quality_list.set_choices(choices, video.formats)
        self._quality_card.setVisible(True)
        self.download_btn.setEnabled(True)

    def _on_analysis_failed(self, message: str) -> None:
        self.analyze_btn.setEnabled(True)
        self.analyze_status_label.setText(message)
        self._current_video = None

    def _on_quality_selection_changed(self, index: int) -> None:
        choice = self.quality_list.current_choice()
        self.mp3_checkbox.setVisible(bool(choice and choice.stream_type == StreamType.AUDIO_ONLY))

    # ------------------------------------------------------------------
    # Destination folder
    # ------------------------------------------------------------------
    def _on_browse_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose Download Folder", self._download_folder)
        if not chosen:
            return
        self._download_folder = chosen
        self.folder_label.setText(chosen)
        self.use_as_default_checkbox.setVisible(True)
        self.use_as_default_checkbox.setChecked(True)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def _on_download_clicked(self) -> None:
        if self._is_playlist_mode:
            self._on_download_playlist_clicked()
            return

        if self._current_video is None:
            return

        choice = self.quality_list.current_choice()
        if choice is None:
            QMessageBox.warning(self, "No Quality Selected", "Please choose a download quality.")
            return

        if not is_writable_directory(self._download_folder):
            QMessageBox.warning(
                self, "Invalid Folder", "The selected download folder is not writable. Please choose another."
            )
            return

        if self.use_as_default_checkbox.isChecked():
            self._settings_manager.set_download_folder(self._download_folder)
            self._settings_manager.sync()

        bitrate_text = self._settings_manager.get_audio_quality()
        try:
            bitrate = int(bitrate_text.split()[0])
        except (ValueError, IndexError):
            bitrate = 192

        request = DownloadRequest(
            url=self._current_video.webpage_url,
            title=self._current_video.title,
            quality=choice,
            destination_dir=self._download_folder,
            convert_to_mp3=self.mp3_checkbox.isChecked() and choice.stream_type == StreamType.AUDIO_ONLY,
            mp3_bitrate_kbps=bitrate,
        )

        self._current_history_id = self._history_service.add_entry(
            request.title,
            request.quality.label,
            "",
            STATUS_DOWNLOADING,
            url=request.url,
            destination_dir=request.destination_dir,
        )

        self.progress_widget.reset()
        self.playlist_item_label.setVisible(False)
        self.open_file_btn.setVisible(True)
        self._pages.setCurrentIndex(_PAGE_DOWNLOADING)
        self._download_controller.start(request)

    def _on_download_playlist_clicked(self) -> None:
        if self._current_playlist is None:
            return

        selected_entries = self.playlist_panel.selected_entries()
        if not selected_entries:
            QMessageBox.warning(self, "No Videos Selected", "Please select at least one video to download.")
            return

        quality = self.playlist_panel.selected_quality()
        if quality is None:
            QMessageBox.warning(self, "No Quality Selected", "Please choose a download quality.")
            return

        if not is_writable_directory(self._download_folder):
            QMessageBox.warning(
                self, "Invalid Folder", "The selected download folder is not writable. Please choose another."
            )
            return

        if self.use_as_default_checkbox.isChecked():
            self._settings_manager.set_download_folder(self._download_folder)
            self._settings_manager.sync()

        bitrate_text = self._settings_manager.get_audio_quality()
        try:
            bitrate = int(bitrate_text.split()[0])
        except (ValueError, IndexError):
            bitrate = 192

        convert_to_mp3 = self.playlist_panel.convert_to_mp3()
        requests = [
            DownloadRequest(
                url=entry.url,
                title=entry.title,
                quality=quality,
                destination_dir=self._download_folder,
                convert_to_mp3=convert_to_mp3,
                mp3_bitrate_kbps=bitrate,
            )
            for entry in selected_entries
        ]

        self._is_resume_mode = False
        self._resume_history_ids = []
        self._playlist_history_ids = [None] * len(requests)

        self.progress_widget.reset()
        self.playlist_item_label.setVisible(True)
        self.open_file_btn.setVisible(False)
        self._pages.setCurrentIndex(_PAGE_DOWNLOADING)
        self._playlist_download_controller.start(requests)

    def _on_cancel_clicked(self) -> None:
        self.cancel_btn.setEnabled(False)
        if self._is_playlist_mode:
            self._playlist_download_controller.cancel()
        else:
            self._download_controller.cancel()

    def _on_download_progress(self, update) -> None:
        self.progress_widget.apply_update(update)

    def _on_download_finished(self, file_path: str) -> None:
        self.cancel_btn.setEnabled(True)
        self._last_finished_path = file_path
        self._pages.setCurrentIndex(_PAGE_COMPLETE)
        self.complete_label.setText("Download completed successfully")

        choice = self.quality_list.current_choice()
        quality_label = choice.label if choice else "Unknown"
        title = self._current_video.title if self._current_video else os.path.basename(file_path)
        if self._current_history_id is not None:
            self._history_service.update_status(self._current_history_id, STATUS_COMPLETED, file_path)
        else:
            self._history_service.add_entry(title, quality_label, file_path, STATUS_COMPLETED)
        self._current_history_id = None

        self._maybe_notify_completion(title)

        if self._settings_manager.get_auto_open_folder():
            self._open_finished_folder()

    def _on_download_failed(self, message: str) -> None:
        self.cancel_btn.setEnabled(True)
        self._pages.setCurrentIndex(_PAGE_IDLE)

        if self._current_history_id is not None:
            self._history_service.update_status(self._current_history_id, STATUS_FAILED)
        elif self._current_video is not None:
            choice = self.quality_list.current_choice()
            quality_label = choice.label if choice else "Unknown"
            self._history_service.add_entry(self._current_video.title, quality_label, "", STATUS_FAILED)
        self._current_history_id = None

        QMessageBox.critical(self, "Download Failed", message)

    def _on_download_cancelled(self) -> None:
        self.cancel_btn.setEnabled(True)
        self._pages.setCurrentIndex(_PAGE_IDLE)
        self.analyze_status_label.setText("Download cancelled.")

        if self._current_history_id is not None:
            self._history_service.update_status(self._current_history_id, STATUS_CANCELLED)
            self._current_history_id = None

        if self._is_resume_mode:
            for history_id in self._resume_history_ids:
                self._history_service.update_status(history_id, STATUS_CANCELLED)
            self._is_resume_mode = False
            self._resume_history_ids = []
        else:
            for history_id in self._playlist_history_ids:
                if history_id is not None:
                    self._history_service.update_status(history_id, STATUS_CANCELLED)
            self._playlist_history_ids = []

    # ------------------------------------------------------------------
    # Playlist download progress/completion
    # ------------------------------------------------------------------
    def _on_playlist_item_started(self, position: int, total: int, title: str) -> None:
        self.playlist_item_label.setText(f"Video {position} of {total}: {title}")
        self.progress_widget.reset()

        if self._is_resume_mode:
            return  # this item's "Downloading" history row already exists

        index = position - 1
        if 0 <= index < len(self._playlist_history_ids):
            entries = self.playlist_panel.selected_entries()
            quality = self.playlist_panel.selected_quality()
            quality_label = quality.label if quality else "Unknown"
            url = entries[index].url if 0 <= index < len(entries) else ""
            history_id = self._history_service.add_entry(
                title, quality_label, "", STATUS_DOWNLOADING, url=url, destination_dir=self._download_folder
            )
            self._playlist_history_ids[index] = history_id

    def _on_playlist_item_finished(self, position: int, file_path: str) -> None:
        index = position - 1
        if self._is_resume_mode:
            if 0 <= index < len(self._resume_history_ids):
                self._history_service.update_status(self._resume_history_ids[index], STATUS_COMPLETED, file_path)
        elif 0 <= index < len(self._playlist_history_ids) and self._playlist_history_ids[index] is not None:
            self._history_service.update_status(self._playlist_history_ids[index], STATUS_COMPLETED, file_path)
        self._last_finished_path = file_path

    def _on_playlist_item_failed(self, position: int, message: str) -> None:
        index = position - 1
        if self._is_resume_mode:
            if 0 <= index < len(self._resume_history_ids):
                self._history_service.update_status(self._resume_history_ids[index], STATUS_FAILED)
        elif 0 <= index < len(self._playlist_history_ids) and self._playlist_history_ids[index] is not None:
            self._history_service.update_status(self._playlist_history_ids[index], STATUS_FAILED)
        logger.warning("Playlist item %d failed: %s", position, message)

    def _on_playlist_finished(self, succeeded: int, failed: int) -> None:
        self.cancel_btn.setEnabled(True)
        self.playlist_item_label.setVisible(False)
        self._pages.setCurrentIndex(_PAGE_COMPLETE)

        if failed:
            self.complete_label.setText(f"Playlist download finished: {succeeded} succeeded, {failed} failed")
        else:
            self.complete_label.setText(f"Playlist download completed successfully ({succeeded} videos)")

        default_title = "Resumed downloads" if self._is_resume_mode else "Playlist"
        self._maybe_notify_completion(self._current_playlist.title if self._current_playlist else default_title)

        self._is_resume_mode = False
        self._resume_history_ids = []

        if self._settings_manager.get_auto_open_folder():
            _open_path(self._download_folder)

    def _maybe_notify_completion(self, title: str) -> None:
        tray_icon = QSystemTrayIcon(self)
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray_icon.show()
            tray_icon.showMessage("Download Complete", title, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _open_finished_file(self) -> None:
        if self._last_finished_path and os.path.isfile(self._last_finished_path):
            _open_path(self._last_finished_path)

    def _open_finished_folder(self) -> None:
        if self._last_finished_path:
            folder = os.path.dirname(self._last_finished_path)
            if os.path.isdir(folder):
                _open_path(folder)

    def _on_download_another(self) -> None:
        self._pages.setCurrentIndex(_PAGE_IDLE)
        self.url_edit.clear()
        self.analyze_status_label.setText("")
        self._current_video = None
        self._current_playlist = None
        self._is_playlist_mode = False
        self._current_history_id = None
        self._playlist_history_ids = []
        self._is_resume_mode = False
        self._resume_history_ids = []
        self._video_info_card.setVisible(False)
        self._quality_card.setVisible(False)
        self._playlist_card.setVisible(False)
        self.download_btn.setEnabled(False)
        self.download_btn.setText("Download")
        self.open_file_btn.setVisible(True)
        self.playlist_item_label.setVisible(False)
        self.progress_widget.reset()

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings_manager, self)
        if dialog.exec():
            self._download_folder = self._settings_manager.get_download_folder()
            self.folder_label.setText(self._download_folder)
            self.use_as_default_checkbox.setVisible(False)

            app = QApplication.instance()
            if app is not None:
                apply_theme(app, self._settings_manager.get_theme())
            self._update_theme_toggle_icon()

    def _open_history(self) -> None:
        dialog = HistoryDialog(self._history_service, self)
        dialog.retry_requested.connect(lambda url, quality_label: (dialog.accept(), self._on_retry_requested(url, quality_label)))
        dialog.exec()

    # ------------------------------------------------------------------
    # Window geometry persistence
    # ------------------------------------------------------------------
    def _restore_window_geometry(self) -> None:
        if not self._settings_manager.get_remember_window_position():
            return
        geometry = self._settings_manager.get_window_geometry()
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._download_controller.is_running or self._playlist_download_controller.is_running:
            reply = QMessageBox.question(
                self,
                "Download In Progress",
                "A download is still in progress. Cancel it and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._download_controller.cancel()
            self._playlist_download_controller.cancel()

        if self._settings_manager.get_remember_window_position():
            self._settings_manager.set_window_geometry(self.saveGeometry())
            self._settings_manager.sync()

        super().closeEvent(event)


def _open_path(path: str) -> None:
    import subprocess

    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - user-chosen local path
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except OSError as exc:
        logger.warning("Could not open path %s: %s", path, exc)
