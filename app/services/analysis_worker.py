"""QThread-friendly wrapper around YtdlpService.extract_info so URL analysis
never blocks the UI thread."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

from app.models.video_info import VideoInfo
from app.services.exceptions import AppError
from app.services.ytdlp_service import YtdlpService
from app.utils.logger import get_logger

logger = get_logger()


class _AnalysisWorker(QObject):
    succeeded = Signal(object)  # VideoInfo
    failed = Signal(str)

    def __init__(self, url: str, service: YtdlpService, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._url = url
        self._service = service

    def run(self) -> None:
        try:
            info = self._service.extract_info(self._url)
        except AppError as exc:
            self.failed.emit(exc.user_message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error analyzing video")
            self.failed.emit(f"An unexpected error occurred: {exc}")
        else:
            self.succeeded.emit(info)


class AnalysisController(QObject):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = YtdlpService()
        self._thread: Optional[QThread] = None
        self._worker: Optional[_AnalysisWorker] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def analyze(self, url: str) -> None:
        if self.is_running:
            return

        self._thread = QThread()
        self._worker = _AnalysisWorker(url, self._service)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)

        self._thread.start()

    def _teardown(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    def _on_succeeded(self, info: VideoInfo) -> None:
        self.succeeded.emit(info)
        self._teardown()

    def _on_failed(self, message: str) -> None:
        self.failed.emit(message)
        self._teardown()
