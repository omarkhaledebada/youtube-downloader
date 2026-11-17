"""Download History dialog backed by HistoryService (SQLite)."""
from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.history_service import HistoryEntry, HistoryService

_STATUS_FILTER_OPTIONS = ["All", "Completed", "Failed", "Downloading", "Cancelled"]


class HistoryDialog(QDialog):
    # Emitted when the user asks to retry a failed download: (url, quality_label).
    retry_requested = Signal(str, str)

    def __init__(self, history_service: HistoryService, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._history_service = history_service
        self._entries: List[HistoryEntry] = []
        self.setWindowTitle("Download History")
        self.resize(760, 460)
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by title...")
        self.search_edit.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self.search_edit, 1)

        filter_row.addWidget(QLabel("Status"))
        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItems(_STATUS_FILTER_OPTIONS)
        self.status_filter_combo.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self.status_filter_combo)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Title", "Downloaded", "Quality", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        self.open_file_btn = QPushButton("Open File")
        self.open_file_btn.clicked.connect(self._open_selected_file)
        button_row.addWidget(self.open_file_btn)

        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.clicked.connect(self._open_selected_folder)
        button_row.addWidget(self.open_folder_btn)

        self.retry_btn = QPushButton("Retry")
        self.retry_btn.clicked.connect(self._retry_selected)
        button_row.addWidget(self.retry_btn)

        self.remove_btn = QPushButton("Remove From History")
        self.remove_btn.clicked.connect(self._remove_selected)
        button_row.addWidget(self.remove_btn)

        button_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)

        layout.addLayout(button_row)

    def reload(self) -> None:
        self._entries = self._history_service.list_entries()
        self._apply_filters()

    def _apply_filters(self) -> None:
        search_text = self.search_edit.text().strip().lower()
        status_filter = self.status_filter_combo.currentText()

        filtered = [
            entry
            for entry in self._entries
            if (not search_text or search_text in entry.title.lower())
            and (status_filter == "All" or entry.status == status_filter)
        ]

        self.table.setRowCount(len(filtered))
        for row, entry in enumerate(filtered):
            self.table.setItem(row, 0, self._readonly_item(entry.title, entry.id))
            self.table.setItem(row, 1, self._readonly_item(entry.downloaded_at.replace("T", " ")))
            self.table.setItem(row, 2, self._readonly_item(entry.quality))
            self.table.setItem(row, 3, self._readonly_item(entry.status))

    @staticmethod
    def _readonly_item(text: str, entry_id: Optional[int] = None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if entry_id is not None:
            item.setData(Qt.ItemDataRole.UserRole, entry_id)
        return item

    def _selected_entry(self) -> Optional[HistoryEntry]:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        entry_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        for entry in self._entries:
            if entry.id == entry_id:
                return entry
        return None

    def _open_selected_file(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        if not entry.file_path or not os.path.isfile(entry.file_path):
            QMessageBox.warning(self, "File Not Found", "This file no longer exists at its saved location.")
            return
        _open_path(entry.file_path)

    def _open_selected_folder(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        folder = os.path.dirname(entry.file_path) if entry.file_path else entry.destination_dir
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Folder Not Found", "This folder no longer exists.")
            return
        _open_path(folder)

    def _retry_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        if not entry.url:
            QMessageBox.warning(
                self,
                "Cannot Retry",
                "This entry was saved before retry support was added and has no stored link.",
            )
            return
        self.retry_requested.emit(entry.url, entry.quality)

    def _remove_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self._history_service.remove_entry(entry.id)
        self.reload()


def _open_path(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 - user-chosen local path, not user-controlled shell string
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except OSError:
        pass
