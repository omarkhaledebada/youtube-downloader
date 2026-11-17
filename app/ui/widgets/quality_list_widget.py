"""Renders the simplified list of download quality choices as radio buttons,
plus a collapsible "Advanced Formats" table showing the raw yt-dlp formats."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.format_option import FormatOption, QualityChoice, StreamType
from app.utils.formatting import format_bytes, format_size_label


class QualityListWidget(QWidget):
    """Emits `selection_changed(int)` with the index into the current
    list of QualityChoice objects whenever the user picks a different one."""

    selection_changed = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._choices: List[QualityChoice] = []
        self._raw_formats: List[FormatOption] = []
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._options_layout = QVBoxLayout()
        self._options_layout.setSpacing(0)
        layout.addLayout(self._options_layout)

        advanced_row = QHBoxLayout()
        self._advanced_toggle = QToolButton()
        self._advanced_toggle.setText("Advanced Formats  ▾")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._advanced_toggle.toggled.connect(self._on_advanced_toggled)
        advanced_row.addWidget(self._advanced_toggle)
        advanced_row.addStretch(1)
        layout.addLayout(advanced_row)

        self._advanced_table = QTableWidget(0, 7)
        self._advanced_table.setHorizontalHeaderLabels(
            ["Format ID", "Ext", "Resolution", "FPS", "Video Codec", "Audio Codec", "Size"]
        )
        self._advanced_table.horizontalHeader().setStretchLastSection(True)
        self._advanced_table.verticalHeader().setVisible(False)
        self._advanced_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._advanced_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._advanced_table.setMinimumHeight(160)
        self._advanced_table.setVisible(False)
        layout.addWidget(self._advanced_table)

    def set_choices(self, choices: List[QualityChoice], raw_formats: List[FormatOption]) -> None:
        self._clear_options()
        self._choices = choices
        self._raw_formats = raw_formats

        for index, choice in enumerate(choices):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 2, 4, 2)

            radio = QRadioButton(self._format_label(choice))
            radio.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self._button_group.addButton(radio, index)
            row_layout.addWidget(radio)

            size_text = format_size_label(choice.estimated_size_bytes, choice.size_is_approximate)
            size_label = QLabel(size_text)
            size_label.setObjectName("VideoMetaLabel")
            row_layout.addWidget(size_label)

            self._options_layout.addWidget(row)

            if index == 0 or choice.is_best_quality:
                radio.setChecked(True)

        if choices:
            # Ensure exactly one is checked (prefer the first "Best Quality" entry).
            self._button_group.buttons()[0].setChecked(True)

        self._button_group.idClicked.connect(self._on_radio_clicked)
        self._populate_advanced_table(raw_formats)

    def _on_radio_clicked(self, index: int) -> None:
        self.selection_changed.emit(index)

    def current_index(self) -> int:
        checked = self._button_group.checkedId()
        return checked if checked >= 0 else -1

    def current_choice(self) -> Optional[QualityChoice]:
        idx = self.current_index()
        if 0 <= idx < len(self._choices):
            return self._choices[idx]
        return None

    def _clear_options(self) -> None:
        for button in self._button_group.buttons():
            self._button_group.removeButton(button)
        while self._options_layout.count():
            item = self._options_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _on_advanced_toggled(self, checked: bool) -> None:
        self._advanced_table.setVisible(checked)
        self._advanced_toggle.setText("Advanced Formats  ▴" if checked else "Advanced Formats  ▾")

    def _populate_advanced_table(self, raw_formats: List[FormatOption]) -> None:
        self._advanced_table.setRowCount(len(raw_formats))
        for row, fmt in enumerate(raw_formats):
            values = [
                fmt.format_id,
                fmt.ext,
                fmt.resolution or "-",
                f"{fmt.fps:g}" if fmt.fps else "-",
                fmt.vcodec if fmt.has_video else "-",
                fmt.acodec if fmt.has_audio else "-",
                format_bytes(fmt.best_known_size) if fmt.best_known_size else "Unknown",
            ]
            for col, value in enumerate(values):
                self._advanced_table.setItem(row, col, QTableWidgetItem(str(value)))

    @staticmethod
    def _format_label(choice: QualityChoice) -> str:
        parts = [choice.label]
        details = []
        if choice.resolution:
            details.append(choice.resolution)
        if choice.fps:
            details.append(f"{int(choice.fps)} FPS")
        if choice.container:
            details.append(choice.container)
        if details:
            parts.append("• " + " • ".join(details))
        if choice.stream_type == StreamType.VIDEO_ONLY:
            parts.append("(Video Only)")
        return "  ".join(parts)
