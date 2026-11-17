"""Light and dark QSS stylesheets for a clean, modern desktop look."""
from __future__ import annotations

_BASE_TEMPLATE = """
QWidget {{
    background-color: {bg};
    color: {fg};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background-color: {bg};
}}

#SurfaceCard {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 10px;
}}

QLabel#TitleLabel {{
    font-size: 20px;
    font-weight: 600;
    color: {fg};
}}

QLabel#SubtitleLabel {{
    font-size: 12px;
    color: {muted};
}}

QLabel#SectionHeader {{
    font-size: 13px;
    font-weight: 600;
    color: {muted};
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}

QLabel#VideoTitleLabel {{
    font-size: 15px;
    font-weight: 600;
}}

QLabel#VideoMetaLabel {{
    font-size: 12px;
    color: {muted};
}}

QLineEdit {{
    background-color: {input_bg};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 9px 12px;
    selection-background-color: {accent};
}}

QLineEdit:focus {{
    border: 1px solid {accent};
}}

QPushButton {{
    background-color: {input_bg};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 8px 16px;
    color: {fg};
}}

QPushButton:hover {{
    background-color: {hover};
}}

QPushButton:pressed {{
    background-color: {pressed};
}}

QPushButton:disabled {{
    color: {muted};
    background-color: {surface};
}}

QPushButton#PrimaryButton {{
    background-color: {accent};
    border: 1px solid {accent};
    color: {accent_fg};
    font-weight: 600;
    padding: 11px 18px;
    border-radius: 10px;
}}

QPushButton#PrimaryButton:hover {{
    background-color: {accent_hover};
}}

QPushButton#PrimaryButton:disabled {{
    background-color: {border};
    border: 1px solid {border};
    color: {muted};
}}

QPushButton#DangerButton {{
    background-color: transparent;
    border: 1px solid {danger};
    color: {danger};
}}

QPushButton#DangerButton:hover {{
    background-color: {danger};
    color: {accent_fg};
}}

QPushButton#IconButton {{
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 6px;
}}

QPushButton#IconButton:hover {{
    background-color: {hover};
}}

QRadioButton {{
    padding: 8px 4px;
    spacing: 10px;
}}

QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 1px solid {border};
    background-color: {input_bg};
}}

QRadioButton::indicator:checked {{
    border: 5px solid {accent};
    background-color: {surface};
}}

QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid {border};
    background-color: {input_bg};
}}

QCheckBox::indicator:checked {{
    background-color: {accent};
    border: 1px solid {accent};
}}

QProgressBar {{
    background-color: {input_bg};
    border: none;
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 6px;
}}

QComboBox {{
    background-color: {input_bg};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 7px 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {surface};
    border: 1px solid {border};
    selection-background-color: {accent};
    selection-color: {accent_fg};
}}

QTableWidget {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 8px;
    gridline-color: {border};
}}

QHeaderView::section {{
    background-color: {surface};
    color: {muted};
    border: none;
    border-bottom: 1px solid {border};
    padding: 6px;
    font-weight: 600;
}}

QScrollArea {{
    border: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}

QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QToolButton {{
    background-color: transparent;
    border: none;
    color: {accent};
}}

QToolButton:hover {{
    color: {accent_hover};
}}

#Divider {{
    background-color: {border};
    max-height: 1px;
    min-height: 1px;
}}

QListWidget {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 8px;
}}

QListWidget::item {{
    padding: 8px;
    border-bottom: 1px solid {border};
}}

QListWidget::item:selected {{
    background-color: {hover};
    color: {fg};
}}
"""

_LIGHT_COLORS = dict(
    bg="#F5F6F8",
    surface="#FFFFFF",
    input_bg="#FFFFFF",
    border="#E1E4E8",
    fg="#1B1F24",
    muted="#6B7280",
    hover="#EEF1F5",
    pressed="#E4E8ED",
    accent="#2563EB",
    accent_hover="#1D4ED8",
    accent_fg="#FFFFFF",
    danger="#DC2626",
)

_DARK_COLORS = dict(
    bg="#15171C",
    surface="#1D2027",
    input_bg="#22252D",
    border="#2E323C",
    fg="#E7E9EC",
    muted="#8B93A1",
    hover="#282C35",
    pressed="#30343E",
    accent="#3B82F6",
    accent_hover="#60A5FA",
    accent_fg="#0B1220",
    danger="#F87171",
)


def light_stylesheet() -> str:
    return _BASE_TEMPLATE.format(**_LIGHT_COLORS)


def dark_stylesheet() -> str:
    return _BASE_TEMPLATE.format(**_DARK_COLORS)


def resolve_effective_theme(app, theme: str) -> str:
    """Resolve "System" to "Light"/"Dark" using the OS color-scheme hint;
    any other value passes through unchanged."""
    if theme != "System":
        return theme
    try:
        from PySide6.QtCore import Qt

        hints = app.styleHints()
        return "Dark" if hints.colorScheme() == Qt.ColorScheme.Dark else "Light"
    except Exception:  # noqa: BLE001
        return "Light"


def apply_theme(app, theme: str) -> None:
    """Apply a theme name ("Light" | "Dark" | "System") to the whole app."""
    effective = resolve_effective_theme(app, theme)
    app.setStyleSheet(dark_stylesheet() if effective == "Dark" else light_stylesheet())
