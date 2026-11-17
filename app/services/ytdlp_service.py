"""Wraps yt-dlp for metadata extraction (analysis without downloading)."""
from __future__ import annotations

from typing import Any, Dict, Optional

import yt_dlp

from app.models.playlist_info import PlaylistEntry, PlaylistInfo
from app.models.video_info import VideoInfo
from app.services.error_mapping import classify_download_error
from app.services.exceptions import ExtractionError, InvalidUrlError
from app.services.format_processor import build_format_options
from app.utils.ffmpeg_locator import get_ffmpeg_directory
from app.utils.logger import get_logger
from app.utils.validators import extract_playlist_id, normalize_youtube_url, is_valid_youtube_url

logger = get_logger()


class YtdlpService:
    """Stateless service for talking to yt-dlp. Safe to call from a worker thread."""

    def _base_opts(self) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "nocheckcertificate": False,
            "socket_timeout": 20,
        }
        ffmpeg_dir = get_ffmpeg_directory()
        if ffmpeg_dir:
            opts["ffmpeg_location"] = ffmpeg_dir
        return opts

    def extract_info(self, url: str) -> VideoInfo:
        """Fetch metadata + formats for a single YouTube video URL.

        Raises a typed AppError subclass on any recognizable failure.
        """
        if not is_valid_youtube_url(url):
            raise InvalidUrlError()

        normalized_url = normalize_youtube_url(url)

        try:
            with yt_dlp.YoutubeDL(self._base_opts()) as ydl:
                raw_info = ydl.extract_info(normalized_url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise classify_download_error(exc) from exc
        except Exception as exc:  # noqa: BLE001 - map anything unexpected to a clean error
            logger.exception("Unexpected error extracting video info")
            raise ExtractionError(str(exc)) from exc

        if raw_info is None:
            raise ExtractionError()

        # A playlist/URL that resolves to multiple entries: take the first video.
        if raw_info.get("_type") == "playlist":
            entries = raw_info.get("entries") or []
            if not entries:
                raise ExtractionError("No video found at this URL.")
            raw_info = entries[0]

        return self._to_video_info(raw_info)

    def _to_video_info(self, raw: Dict[str, Any]) -> VideoInfo:
        raw_formats = raw.get("formats") or []
        format_options = build_format_options(raw_formats)

        return VideoInfo(
            video_id=raw.get("id", ""),
            title=raw.get("title") or "Untitled video",
            channel=raw.get("channel") or raw.get("uploader") or "Unknown channel",
            duration_seconds=int(raw.get("duration") or 0),
            thumbnail_url=raw.get("thumbnail"),
            upload_date=raw.get("upload_date"),
            view_count=raw.get("view_count"),
            webpage_url=raw.get("webpage_url") or raw.get("original_url") or "",
            formats=format_options,
            raw_formats=raw_formats,
        )

    def extract_basic_info(self, url: str) -> Dict[str, Any]:
        """Lightweight lookup of just id/title for a single video URL --
        used by the batch queue and by resuming interrupted downloads,
        where we need a real title for the filename but fetching the full
        format list for every URL up front would be needless overhead.
        """
        if not is_valid_youtube_url(url):
            raise InvalidUrlError()

        normalized_url = normalize_youtube_url(url)
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extract_flat": True,
            "skip_download": True,
            "socket_timeout": 20,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                raw_info = ydl.extract_info(normalized_url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise classify_download_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error fetching basic video info")
            raise ExtractionError(str(exc)) from exc

        if raw_info is None:
            raise ExtractionError()

        return {"id": raw_info.get("id", ""), "title": raw_info.get("title") or url}

    def extract_playlist_info(self, url: str) -> PlaylistInfo:
        """Fetch a lightweight listing of every video in a playlist (titles,
        durations, thumbnails) without pulling each video's full format list
        -- that would mean one extra network round-trip per video, which is
        far too slow for playlists of any real size.
        """
        playlist_id = extract_playlist_id(url)
        if playlist_id is None:
            raise InvalidUrlError("This URL does not contain a playlist.")

        normalized_url = normalize_youtube_url(url)

        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "ignoreerrors": True,
            "socket_timeout": 20,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                raw_info = ydl.extract_info(normalized_url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise classify_download_error(exc) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error extracting playlist info")
            raise ExtractionError(str(exc)) from exc

        if raw_info is None:
            raise ExtractionError("Could not read this playlist.")

        raw_entries = raw_info.get("entries") or []
        entries: list[PlaylistEntry] = []
        for index, raw_entry in enumerate(raw_entries, start=1):
            if not raw_entry:
                continue  # a deleted/private/unavailable video in the playlist
            video_id = raw_entry.get("id")
            if not video_id:
                continue

            thumbnails = raw_entry.get("thumbnails") or []
            thumbnail_url = thumbnails[-1]["url"] if thumbnails else raw_entry.get("thumbnail")

            entries.append(
                PlaylistEntry(
                    index=index,
                    video_id=video_id,
                    title=raw_entry.get("title") or f"Video {index}",
                    url=raw_entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                    duration_seconds=raw_entry.get("duration"),
                    thumbnail_url=thumbnail_url,
                )
            )

        if not entries:
            raise ExtractionError("This playlist has no downloadable videos.")

        return PlaylistInfo(
            playlist_id=playlist_id,
            title=raw_info.get("title") or "Untitled playlist",
            uploader=raw_info.get("uploader") or raw_info.get("channel"),
            entries=entries,
        )
