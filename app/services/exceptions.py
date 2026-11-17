"""Typed exceptions used across services so the UI can present clear,
user-friendly messages instead of raw tracebacks."""
from __future__ import annotations


class AppError(Exception):
    """Base class for all application-raised errors."""

    user_message = "An unexpected error occurred."

    def __init__(self, message: str | None = None):
        super().__init__(message or self.user_message)
        if message:
            self.user_message = message


class InvalidUrlError(AppError):
    user_message = "The URL does not appear to be a valid YouTube video URL."


class VideoUnavailableError(AppError):
    user_message = "This video is unavailable."


class PrivateVideoError(AppError):
    user_message = "This video is private and cannot be downloaded."


class VideoRemovedError(AppError):
    user_message = "This video has been removed or no longer exists."


class GeoRestrictedError(AppError):
    user_message = "This video is not available in your region."


class NetworkError(AppError):
    user_message = "Unable to connect to YouTube. Check your internet connection and try again."


class FfmpegMissingError(AppError):
    user_message = (
        "FFmpeg was not found. Merging video and audio, and converting to MP3, "
        "requires FFmpeg. Please install FFmpeg or place ffmpeg.exe next to the "
        "application, then try again."
    )


class DownloadCancelledError(AppError):
    user_message = "Download was cancelled."


class ExtractionError(AppError):
    user_message = "Could not read information for this video."
