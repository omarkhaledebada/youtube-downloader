"""Download orchestration: runs yt-dlp on a background QThread, reports
fine-grained progress (including distinct video/audio/merge phases) via
Qt signals, and supports clean cancellation.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional

import yt_dlp
from PySide6.QtCore import QObject, QThread, Signal

from app.models.format_option import QualityChoice, StreamType
from app.services.error_mapping import classify_download_error
from app.services.exceptions import AppError, DownloadCancelledError, FfmpegMissingError
from app.services.ffmpeg_service import FfmpegService
from app.utils.ffmpeg_locator import get_ffmpeg_directory
from app.utils.logger import get_logger
from app.utils.sanitize import sanitize_filename, unique_path

logger = get_logger()


class _CancelledSignal(Exception):
    """Raised from inside a yt-dlp hook to unwind the download cleanly."""


@dataclass
class DownloadRequest:
    url: str
    title: str
    quality: QualityChoice
    destination_dir: str
    convert_to_mp3: bool = False
    mp3_bitrate_kbps: int = 192


@dataclass
class ProgressUpdate:
    phase: str  # "video" | "audio" | "merging" | "converting" | "starting"
    status_text: str
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    speed_bytes_per_sec: Optional[float] = None
    eta_seconds: Optional[float] = None
    percent: Optional[float] = None


class DownloadWorker(QObject):
    """Runs a single download+merge/convert job. Intended to live on a QThread."""

    progress = Signal(object)  # ProgressUpdate
    finished = Signal(str)  # final file path
    failed = Signal(str)  # user-facing error message
    cancelled = Signal()

    def __init__(self, request: DownloadRequest, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._request = request
        self._cancel_event = threading.Event()
        self._ffmpeg_service = FfmpegService()
        self._video_done = False
        self._final_path: Optional[str] = None

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            self._run_impl()
        except _CancelledSignal:
            logger.info("Download cancelled by user: %s", self._request.url)
            self.cancelled.emit()
        except AppError as exc:
            logger.warning("Download failed: %s", exc.user_message)
            self.failed.emit(exc.user_message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error during download")
            self.failed.emit(f"An unexpected error occurred: {exc}")

    # ------------------------------------------------------------------
    def _run_impl(self) -> None:
        request = self._request
        quality = request.quality

        needs_ffmpeg = quality.requires_merge or request.convert_to_mp3
        if needs_ffmpeg and not self._ffmpeg_service.is_available():
            raise FfmpegMissingError()

        os.makedirs(request.destination_dir, exist_ok=True)

        # Download under a safe, collision-proof temp name (video id based),
        # then move/rename to the final sanitized, human-readable filename.
        video_id = _safe_component(request.url)
        temp_template = os.path.join(request.destination_dir, f".{video_id}.%(ext)s")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": quality.format_selector,
            "outtmpl": temp_template,
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            "noprogress": True,
            "retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 20,
        }

        ffmpeg_dir = get_ffmpeg_directory()
        if ffmpeg_dir:
            ydl_opts["ffmpeg_location"] = ffmpeg_dir

        postprocessors = []
        final_ext = self._expected_extension()

        if quality.stream_type == StreamType.AUDIO_ONLY:
            if request.convert_to_mp3:
                postprocessors.append(
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": str(request.mp3_bitrate_kbps),
                    }
                )
        else:
            if quality.requires_merge:
                ydl_opts["merge_output_format"] = "mp4"
            elif quality.container.lower() not in ("mp4",):
                # Progressive stream in a non-mp4 container: leave as-is,
                # container label already reflects the true format.
                pass

        if postprocessors:
            ydl_opts["postprocessors"] = postprocessors

        self._emit_progress("starting", "Preparing download...")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            if self._cancel_event.is_set():
                raise _CancelledSignal() from exc
            raise classify_download_error(exc) from exc

        if self._cancel_event.is_set():
            raise _CancelledSignal()

        produced_path = self._resolve_output_path(info, request.destination_dir, video_id, final_ext)
        if produced_path is None or not os.path.isfile(produced_path):
            raise AppError("The download finished but the output file could not be located.")

        final_name = sanitize_filename(request.title) + os.path.splitext(produced_path)[1]
        final_path = unique_path(request.destination_dir, final_name)

        try:
            os.replace(produced_path, final_path)
        except OSError as exc:
            logger.warning("Could not rename output file, keeping temp name: %s", exc)
            final_path = produced_path

        self._final_path = final_path
        self._emit_progress("done", "Completed", percent=1.0)
        self.finished.emit(final_path)

    # ------------------------------------------------------------------
    def _expected_extension(self) -> str:
        quality = self._request.quality
        if quality.stream_type == StreamType.AUDIO_ONLY:
            return "mp3" if self._request.convert_to_mp3 else (quality.audio_format.ext if quality.audio_format else "m4a")
        if quality.requires_merge:
            return "mp4"
        return quality.video_format.ext if quality.video_format else "mp4"

    def _resolve_output_path(self, info: dict, directory: str, video_id: str, expected_ext: str) -> Optional[str]:
        # Newer yt-dlp exposes the final file(s) via 'requested_downloads'.
        requested = info.get("requested_downloads") if isinstance(info, dict) else None
        if requested:
            path = requested[-1].get("filepath")
            if path and os.path.isfile(path):
                return path

        # Fall back to scanning the temp-named file with the expected extension.
        candidate = os.path.join(directory, f".{video_id}.{expected_ext}")
        if os.path.isfile(candidate):
            return candidate

        # Last resort: scan for any file starting with the temp prefix.
        prefix = f".{video_id}."
        for name in os.listdir(directory):
            if name.startswith(prefix):
                return os.path.join(directory, name)
        return None

    # ------------------------------------------------------------------
    def _progress_hook(self, d: dict) -> None:
        if self._cancel_event.is_set():
            raise _CancelledSignal()

        status = d.get("status")
        info = d.get("info_dict") or {}
        is_audio_phase = (not info.get("vcodec") or info.get("vcodec") == "none") and info.get("acodec") not in (None, "none")
        phase = "audio" if is_audio_phase else "video"

        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            speed = d.get("speed")
            eta = d.get("eta")
            percent = (downloaded / total) if total else None
            label = "Downloading audio..." if phase == "audio" else "Downloading video..."
            self._emit_progress(
                phase,
                label,
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed_bytes_per_sec=speed,
                eta_seconds=eta,
                percent=percent,
            )
        elif status == "finished":
            if phase == "video":
                self._video_done = True
            label = "Audio downloaded" if phase == "audio" else "Video downloaded"
            self._emit_progress(phase, label, percent=1.0)
        elif status == "error":
            pass  # surfaced via the DownloadError raised by yt-dlp itself

    def _postprocessor_hook(self, d: dict) -> None:
        if self._cancel_event.is_set():
            raise _CancelledSignal()

        status = d.get("status")
        pp_name = d.get("postprocessor", "")

        if status == "started":
            if "Merger" in pp_name:
                self._emit_progress("merging", "Merging video and audio...")
            elif "ExtractAudio" in pp_name:
                self._emit_progress("converting", "Converting audio...")
            elif "Remuxer" in pp_name or "Recode" in pp_name:
                self._emit_progress("merging", "Finalizing file...")
        elif status == "finished":
            if "Merger" in pp_name:
                self._emit_progress("merging", "Merge complete", percent=1.0)
            elif "ExtractAudio" in pp_name:
                self._emit_progress("converting", "Conversion complete", percent=1.0)

    def _emit_progress(self, phase: str, text: str, **kwargs) -> None:
        update = ProgressUpdate(phase=phase, status_text=text, **kwargs)
        self.progress.emit(update)


def _safe_component(url: str) -> str:
    """Derive a filesystem-safe temp basename from a URL (falls back to a hash)."""
    import hashlib
    import re

    match = re.search(r"(?:v=|/shorts/|/live/|youtu\.be/|/embed/)([A-Za-z0-9_-]{6,})", url)
    if match:
        return match.group(1)
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


class DownloadController(QObject):
    """Owns the QThread/DownloadWorker lifecycle so the UI only deals with
    one long-lived object per download."""

    progress = Signal(object)
    finished = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._worker: Optional[DownloadWorker] = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, request: DownloadRequest) -> None:
        if self.is_running:
            raise RuntimeError("A download is already in progress.")

        self._thread = QThread()
        self._worker = DownloadWorker(request)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.emit)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)

        self._thread.start()

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def _teardown(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None

    def _on_finished(self, path: str) -> None:
        # Tear the old thread/worker down BEFORE telling listeners we're
        # finished: a listener (e.g. the playlist controller) may react by
        # immediately starting the next download on this same controller,
        # and `start()` refuses to run while the previous thread is still
        # alive. Tearing down first guarantees `is_running` is already
        # False by the time any such listener runs.
        self._teardown()
        self.finished.emit(path)

    def _on_failed(self, message: str) -> None:
        self._teardown()
        self.failed.emit(message)

    def _on_cancelled(self) -> None:
        self._teardown()
        self.cancelled.emit()
