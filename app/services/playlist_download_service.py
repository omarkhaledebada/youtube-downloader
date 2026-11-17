"""Sequential playlist download orchestration.

Downloads each selected playlist video one at a time, reusing the same
DownloadController/DownloadWorker as single-video downloads, so merging,
MP3 conversion, cancellation, and progress reporting all behave identically
per item. A failure on one video does not stop the rest of the playlist --
it is recorded and the queue continues.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from app.services.download_service import DownloadController, DownloadRequest


class PlaylistDownloadController(QObject):
    item_started = Signal(int, int, str)  # position (1-based), total, title
    item_progress = Signal(object)  # ProgressUpdate, passthrough for the current item
    item_finished = Signal(int, str)  # position, final file path
    item_failed = Signal(int, str)  # position, message
    finished = Signal(int, int)  # succeeded_count, failed_count
    cancelled = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._controller = DownloadController(self)
        self._controller.progress.connect(self.item_progress.emit)
        self._controller.finished.connect(self._on_item_finished)
        self._controller.failed.connect(self._on_item_failed)
        self._controller.cancelled.connect(self._on_item_cancelled)

        self._queue: List[DownloadRequest] = []
        self._current_index = -1
        self._succeeded = 0
        self._failed = 0
        self._cancel_requested = False

    @property
    def is_running(self) -> bool:
        return self._controller.is_running

    def start(self, requests: List[DownloadRequest]) -> None:
        if self.is_running or not requests:
            return
        self._queue = requests
        self._current_index = -1
        self._succeeded = 0
        self._failed = 0
        self._cancel_requested = False
        self._advance()

    def cancel(self) -> None:
        self._cancel_requested = True
        self._controller.cancel()

    def _advance(self) -> None:
        if self._cancel_requested:
            self.cancelled.emit()
            return

        self._current_index += 1
        if self._current_index >= len(self._queue):
            self.finished.emit(self._succeeded, self._failed)
            return

        request = self._queue[self._current_index]
        self.item_started.emit(self._current_index + 1, len(self._queue), request.title)
        self._controller.start(request)

    def _on_item_finished(self, path: str) -> None:
        self._succeeded += 1
        self.item_finished.emit(self._current_index + 1, path)
        self._advance()

    def _on_item_failed(self, message: str) -> None:
        self._failed += 1
        self.item_failed.emit(self._current_index + 1, message)
        self._advance()

    def _on_item_cancelled(self) -> None:
        # Cancelling the current item cancels the whole playlist queue.
        self.cancelled.emit()
