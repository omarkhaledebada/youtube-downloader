"""Displays the analyzed video's thumbnail, title, channel, and duration."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.models.video_info import VideoInfo

_THUMB_SIZE = QSize(176, 99)


class VideoInfoWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._network_manager = QNetworkAccessManager(self)
        self._reply: Optional[QNetworkReply] = None
        self._build_ui()
        self.clear()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(_THUMB_SIZE)
        self.thumbnail_label.setStyleSheet(
            "background-color: rgba(120,120,120,40); border-radius: 8px;"
        )
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setScaledContents(False)
        layout.addWidget(self.thumbnail_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        self.title_label = QLabel()
        self.title_label.setObjectName("VideoTitleLabel")
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_layout.addWidget(self.title_label)

        self.channel_label = QLabel()
        self.channel_label.setObjectName("VideoMetaLabel")
        text_layout.addWidget(self.channel_label)

        self.meta_label = QLabel()
        self.meta_label.setObjectName("VideoMetaLabel")
        text_layout.addWidget(self.meta_label)

        text_layout.addStretch(1)
        layout.addLayout(text_layout, 1)

    def clear(self) -> None:
        self.thumbnail_label.clear()
        self.title_label.setText("")
        self.channel_label.setText("")
        self.meta_label.setText("")
        self.setVisible(False)

    def display(self, video: VideoInfo) -> None:
        self.setVisible(True)
        self.title_label.setText(video.title)
        self.channel_label.setText(video.channel)

        meta_parts = [f"Duration: {video.duration_display}"]
        if video.upload_date_display:
            meta_parts.append(video.upload_date_display)
        if video.view_count_display:
            meta_parts.append(video.view_count_display)
        self.meta_label.setText("  ·  ".join(meta_parts))

        self.thumbnail_label.setText("")
        if video.thumbnail_url:
            self._load_thumbnail(video.thumbnail_url)

    def _load_thumbnail(self, url: str) -> None:
        if self._reply is not None:
            self._reply.abort()
            self._reply = None

        request = QNetworkRequest(QUrl(url))
        reply = self._network_manager.get(request)
        self._reply = reply
        reply.finished.connect(lambda: self._on_thumbnail_loaded(reply))

    def _on_thumbnail_loaded(self, reply: QNetworkReply) -> None:
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                scaled = pixmap.scaled(
                    _THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.thumbnail_label.setPixmap(scaled)
        reply.deleteLater()
        if self._reply is reply:
            self._reply = None
