"""Application entry point.

Sets up logging, a global exception hook (so unhandled errors never crash
the app silently), the Qt application, theme, and the main window.
"""
from __future__ import annotations

import sys
import traceback

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config.settings import SettingsManager
from app.ui.main_window import MainWindow
from app.ui.styles import apply_theme
from app.utils.logger import get_logger, setup_logging


def _install_exception_hook(app: QApplication) -> None:
    logger = get_logger()

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        logger.critical("Unhandled exception:\n%s", formatted)

        try:
            QMessageBox.critical(
                None,
                "Unexpected Error",
                "An unexpected error occurred and has been logged.\n\n"
                f"{exc_value}",
            )
        except Exception:  # noqa: BLE001 - never let the handler itself crash
            pass

    sys.excepthook = handle_exception


def main() -> int:
    setup_logging()
    logger = get_logger()
    logger.info("Starting YouTube Downloader")

    app = QApplication(sys.argv)
    app.setApplicationName("YouTube Downloader")
    app.setOrganizationName("HRKLIX")

    _install_exception_hook(app)

    settings_manager = SettingsManager()
    apply_theme(app, settings_manager.get_theme())

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
