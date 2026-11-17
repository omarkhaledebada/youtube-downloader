"""Displays an analyzed playlist: title/count, a checkable list of videos,
Select All / Deselect All, and a generic quality selector."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.format_option import QualityChoice, StreamType
from app.models.playlist_info import PlaylistEntry, PlaylistInfo
from app.services.format_processor import build_playlist_quality_choices


class PlaylistPanel(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._entries: List[PlaylistEntry] = []
        self._quality_choices: List[QualityChoice] = build_playlist_quality_choices()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setObjectName("VideoTitleLabel")
        self.title_label.setWordWrap(True)
        header_row.addWidget(self.title_label, 1)
        layout.addLayout(header_row)

        self.count_label = QLabel("")
        self.count_label.setObjectName("VideoMetaLabel")
        layout.addWidget(self.count_label)

        select_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        select_row.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self._deselect_all)
        select_row.addWidget(deselect_all_btn)
        select_row.addStretch(1)
        layout.addLayout(select_row)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_widget.setMinimumHeight(220)
        self.list_widget.setMaximumHeight(320)
        layout.addWidget(self.list_widget)

        quality_row = QHBoxLayout()
        quality_label = QLabel("Quality")
        quality_row.addWidget(quality_label)

        self.quality_combo = QComboBox()
        for choice in self._quality_choices:
            self.quality_combo.addItem(choice.label)
        self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
        quality_row.addWidget(self.quality_combo, 1)
        layout.addLayout(quality_row)

        self.mp3_checkbox = QCheckBox("Convert audio to MP3")
        self.mp3_checkbox.setVisible(False)
        layout.addWidget(self.mp3_checkbox)

    def display(self, playlist: PlaylistInfo) -> None:
        self._entries = playlist.entries
        self.title_label.setText(playlist.title)
        count = playlist.count
        subtitle = f"{count} video{'s' if count != 1 else ''}"
        if playlist.uploader:
            subtitle += f"  ·  {playlist.uploader}"
        self.count_label.setText(subtitle)

        self.list_widget.clear()
        for entry in self._entries:
            item = QListWidgetItem(f"{entry.index}. {entry.title}  ({entry.duration_display})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list_widget.addItem(item)

    def _select_all(self) -> None:
        self._set_all_checked(Qt.CheckState.Checked)

    def _deselect_all(self) -> None:
        self._set_all_checked(Qt.CheckState.Unchecked)

    def _set_all_checked(self, state: Qt.CheckState) -> None:
        for row in range(self.list_widget.count()):
            self.list_widget.item(row).setCheckState(state)

    def selected_entries(self) -> List[PlaylistEntry]:
        selected = []
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected

    def selected_quality(self) -> Optional[QualityChoice]:
        index = self.quality_combo.currentIndex()
        if 0 <= index < len(self._quality_choices):
            return self._quality_choices[index]
        return None

    def convert_to_mp3(self) -> bool:
        quality = self.selected_quality()
        return bool(quality and quality.stream_type == StreamType.AUDIO_ONLY and self.mp3_checkbox.isChecked())

    def _on_quality_changed(self, index: int) -> None:
        quality = self._quality_choices[index] if 0 <= index < len(self._quality_choices) else None
        self.mp3_checkbox.setVisible(bool(quality and quality.stream_type == StreamType.AUDIO_ONLY))
