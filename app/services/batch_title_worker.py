"""QThread-friendly resolver that fetches real titles for a list of URLs
before queueing them for download (used by the batch/queue dialog and by
resuming interrupted downloads whose stored title is missing)."""
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, QThread, Signal

from app.services.ytdlp_service import YtdlpService
from app.utils.logger import get_logger

logger = get_logger()


class _BatchTitleWorker(QObject):
    finished = Signal(list)  # List[Tuple[url, title]]

    def __init__(self, urls: List[str], service: YtdlpService, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._urls = urls
        self._service = service

    def run(self) -> None:
        results: List[Tuple[str, str]] = []
        for url in self._urls:
            title = url
            try:
                info = self._service.extract_basic_info(url)
                title = info.get("title") or url
            except Exception as exc:  # noqa: BLE001 - a bad URL just falls back to itself as the title
                logger.warning("Could not resolve title for %s: %s", url, exc)
            results.append((url, title))
        self.finished.emit(results)


class BatchTitleController(QObject):
    finished = Signal(list)  # List[Tuple[url, title]]

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._service = YtdlpService()
        self._thread: Optional[QThread] = None
        self._worker: Optional[_BatchTitleWorker] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def resolve(self, urls: List[str]) -> None:
        if self.is_running:
            return

        self._thread = QThread()
        self._worker = _BatchTitleWorker(urls, self._service)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)

        self._thread.start()

    def _teardown(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    def _on_finished(self, results: list) -> None:
        self._teardown()
        self.finished.emit(results)
