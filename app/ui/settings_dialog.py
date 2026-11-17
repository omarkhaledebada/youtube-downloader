"""Simple Settings dialog: default folder, default quality/format, audio
quality, and behaviour toggles. All changes are saved on Accept."""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import (
    DEFAULT_AUDIO_QUALITY_OPTIONS,
    DEFAULT_FORMAT_OPTIONS,
    DEFAULT_QUALITY_OPTIONS,
    THEME_OPTIONS,
    SettingsManager,
)
from app.utils.validators import is_writable_directory


class SettingsDialog(QDialog):
    def __init__(self, settings_manager: SettingsManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings_manager = settings_manager
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)
        self._build_ui()
        self._load_current_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        folder_row.addWidget(self.folder_edit)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_folder)
        folder_row.addWidget(browse_btn)
        folder_widget = QWidget()
        folder_widget.setLayout(folder_row)
        form.addRow("Default Download Folder", folder_widget)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(DEFAULT_QUALITY_OPTIONS)
        form.addRow("Default Video Quality", self.quality_combo)

        self.format_combo = QComboBox()
        self.format_combo.addItems(DEFAULT_FORMAT_OPTIONS)
        form.addRow("Default Format", self.format_combo)

        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.addItems(DEFAULT_AUDIO_QUALITY_OPTIONS)
        form.addRow("Audio Quality", self.audio_quality_combo)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEME_OPTIONS)
        form.addRow("Theme", self.theme_combo)

        layout.addLayout(form)

        self.auto_open_checkbox = QCheckBox("Automatically open folder after download")
        layout.addWidget(self.auto_open_checkbox)

        self.remember_position_checkbox = QCheckBox("Remember window position")
        layout.addWidget(self.remember_position_checkbox)

        self.warning_label = QLabel("")
        self.warning_label.setObjectName("VideoMetaLabel")
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.warning_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_current_values(self) -> None:
        snapshot = self._settings_manager.snapshot()
        self.folder_edit.setText(snapshot.download_folder)
        self._set_combo_value(self.quality_combo, snapshot.default_quality)
        self._set_combo_value(self.format_combo, snapshot.default_format)
        self._set_combo_value(self.audio_quality_combo, snapshot.audio_quality)
        self._set_combo_value(self.theme_combo, snapshot.theme)
        self.auto_open_checkbox.setChecked(snapshot.auto_open_folder)
        self.remember_position_checkbox.setChecked(snapshot.remember_window_position)

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _browse_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose Download Folder", self.folder_edit.text())
        if chosen:
            self.folder_edit.setText(chosen)

    def _on_save(self) -> None:
        folder = self.folder_edit.text().strip()
        if not is_writable_directory(folder):
            self.warning_label.setText("This folder could not be created or is not writable. Please choose another.")
            return

        self._settings_manager.set_download_folder(folder)
        self._settings_manager.set_default_quality(self.quality_combo.currentText())
        self._settings_manager.set_default_format(self.format_combo.currentText())
        self._settings_manager.set_audio_quality(self.audio_quality_combo.currentText())
        self._settings_manager.set_theme(self.theme_combo.currentText())
        self._settings_manager.set_auto_open_folder(self.auto_open_checkbox.isChecked())
        self._settings_manager.set_remember_window_position(self.remember_position_checkbox.isChecked())
        self._settings_manager.sync()
        self.accept()
