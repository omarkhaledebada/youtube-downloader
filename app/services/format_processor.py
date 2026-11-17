"""Turns yt-dlp's raw (often huge and confusing) format list into a small,
understandable set of QualityChoice options for the UI.

Design:
- Raw formats are normalized into FormatOption objects.
- Progressive (video+audio already muxed) formats are preferred when they
  exist at a given resolution and are MP4/H.264 for maximum compatibility.
- When only an adaptive (video-only) stream exists at a resolution, it is
  paired with the best compatible audio-only stream; the pair is merged
  with FFmpeg after downloading. This is exposed to the user as ordinary
  "1080p", "1440p" etc. options -- they never see the split.
- A "Best Quality" option always maps to the highest available resolution.
- An "Audio Only" option maps to the best available audio stream.
- The full raw list remains accessible for "Advanced Formats".
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.models.format_option import FormatOption, QualityChoice, StreamType

# Standard quality ladder we try to surface, highest first.
_QUALITY_LADDER = [2160, 1440, 1080, 720, 480, 360, 240, 144]

_PREFERRED_VIDEO_CODEC_PREFIXES = ("avc1", "h264")  # widest compatibility


def _parse_raw_format(raw: dict) -> Optional[FormatOption]:
    format_id = raw.get("format_id")
    if not format_id:
        return None

    vcodec = raw.get("vcodec")
    acodec = raw.get("acodec")

    # Skip formats that are neither video nor audio (e.g. storyboards).
    if (not vcodec or vcodec == "none") and (not acodec or acodec == "none"):
        return None

    return FormatOption(
        format_id=str(format_id),
        ext=raw.get("ext") or "",
        resolution=raw.get("resolution"),
        width=raw.get("width"),
        height=raw.get("height"),
        fps=raw.get("fps"),
        vcodec=vcodec,
        acodec=acodec,
        filesize=raw.get("filesize"),
        filesize_approx=raw.get("filesize_approx"),
        tbr=raw.get("tbr"),
        abr=raw.get("abr"),
        vbr=raw.get("vbr"),
        format_note=raw.get("format_note"),
        protocol=raw.get("protocol"),
    )


def build_format_options(raw_formats: List[dict]) -> List[FormatOption]:
    options = []
    for raw in raw_formats:
        parsed = _parse_raw_format(raw)
        if parsed is not None:
            options.append(parsed)
    return options


def _best_audio(formats: List[FormatOption]) -> Optional[FormatOption]:
    """Pick the best pure-audio stream, preferring m4a for compatibility,
    then falling back to whichever has the highest bitrate."""
    audio_only = [f for f in formats if f.stream_type == StreamType.AUDIO_ONLY]
    if not audio_only:
        return None

    def score(fmt: FormatOption) -> tuple:
        ext_priority = 1 if fmt.ext == "m4a" else 0
        bitrate = fmt.abr or fmt.tbr or 0
        return (ext_priority, bitrate)

    return max(audio_only, key=score)


def _progressive_formats(formats: List[FormatOption]) -> List[FormatOption]:
    return [f for f in formats if f.stream_type == StreamType.VIDEO_AND_AUDIO]


def _video_only_formats(formats: List[FormatOption]) -> List[FormatOption]:
    return [f for f in formats if f.stream_type == StreamType.VIDEO_ONLY]


def _pick_best_for_bucket(candidates: List[FormatOption]) -> Optional[FormatOption]:
    """Among formats targeting the same resolution bucket, prefer widely
    compatible codecs and higher bitrate/fps."""
    if not candidates:
        return None

    def score(fmt: FormatOption) -> tuple:
        codec_priority = 1 if (fmt.vcodec or "").startswith(_PREFERRED_VIDEO_CODEC_PREFIXES) else 0
        fps = fmt.fps or 0
        bitrate = fmt.vbr or fmt.tbr or 0
        return (codec_priority, fps, bitrate)

    return max(candidates, key=score)


def _estimate_pair_size(
    video: FormatOption, audio: Optional[FormatOption], duration_seconds: int = 0
) -> tuple[Optional[int], bool]:
    """Returns (estimated_bytes, is_approximate).

    YouTube frequently omits both `filesize` and `filesize_approx` for
    DASH video/audio streams -- in that case we fall back to bitrate *
    duration (the same formula yt-dlp itself uses when it does fill in
    `filesize_approx`) rather than showing "Unknown" for almost every
    quality, which was giving users no size information at all in
    practice.
    """
    video_size = video.best_known_size
    video_exact = video.filesize is not None
    if video_size is None:
        video_size = video.estimate_size_from_bitrate(duration_seconds)

    audio_size = 0
    audio_exact = True
    if audio is not None:
        audio_size = audio.best_known_size
        audio_exact = audio.filesize is not None
        if audio_size is None:
            audio_size = audio.estimate_size_from_bitrate(duration_seconds)
        if audio_size is None:
            audio_size = 0

    if video_size is None:
        return None, True

    return video_size + audio_size, not (video_exact and audio_exact)


def build_quality_choices(formats: List[FormatOption], duration_seconds: int = 0) -> List[QualityChoice]:
    """Build the simplified list the user sees: Best Quality, 2160p, ... , Audio Only."""
    choices: List[QualityChoice] = []

    progressive = _progressive_formats(formats)
    video_only = _video_only_formats(formats)
    best_audio = _best_audio(formats)

    seen_buckets: Dict[int, QualityChoice] = {}

    for bucket in _QUALITY_LADDER:
        # Prefer a ready-made progressive (video+audio) stream at this bucket.
        progressive_candidates = [f for f in progressive if f.height_bucket == bucket]
        progressive_pick = _pick_best_for_bucket(progressive_candidates)

        video_candidates = [f for f in video_only if f.height_bucket == bucket]
        video_pick = _pick_best_for_bucket(video_candidates)

        chosen: Optional[QualityChoice] = None

        if progressive_pick is not None and video_pick is not None:
            # Prefer whichever gives a better/more complete result; adaptive
            # video-only streams are usually higher bitrate/fps at the same
            # resolution, so prefer the adaptive+merge path when both exist,
            # unless the progressive stream is the only one with a known size.
            use_adaptive = True
        else:
            use_adaptive = video_pick is not None and progressive_pick is None

        if use_adaptive and video_pick is not None:
            size, approx = _estimate_pair_size(video_pick, best_audio, duration_seconds)
            chosen = QualityChoice(
                label=f"{bucket}p",
                resolution=video_pick.resolution or (f"{video_pick.width}x{video_pick.height}" if video_pick.width else None),
                fps=video_pick.fps,
                container="MP4" if (video_pick.ext in ("mp4", "m4a") or (best_audio and best_audio.ext == "m4a")) else video_pick.ext.upper(),
                stream_type=StreamType.VIDEO_AND_AUDIO,
                estimated_size_bytes=size,
                size_is_approximate=approx,
                video_format=video_pick,
                audio_format=best_audio,
                requires_merge=True,
                vcodec=video_pick.vcodec,
                acodec=best_audio.acodec if best_audio else None,
                sort_key=float(bucket),
            )
        elif progressive_pick is not None:
            size = progressive_pick.best_known_size
            approx = progressive_pick.filesize is None
            if size is None:
                size = progressive_pick.estimate_size_from_bitrate(duration_seconds)
            chosen = QualityChoice(
                label=f"{bucket}p",
                resolution=progressive_pick.resolution or (f"{progressive_pick.width}x{progressive_pick.height}" if progressive_pick.width else None),
                fps=progressive_pick.fps,
                container=progressive_pick.ext.upper(),
                stream_type=StreamType.VIDEO_AND_AUDIO,
                estimated_size_bytes=size,
                size_is_approximate=approx,
                video_format=progressive_pick,
                audio_format=None,
                requires_merge=False,
                vcodec=progressive_pick.vcodec,
                acodec=progressive_pick.acodec,
                sort_key=float(bucket),
            )

        if chosen is not None:
            seen_buckets[bucket] = chosen
            choices.append(chosen)

    # "Best Quality" = highest bucket found, presented first.
    if choices:
        best = max(choices, key=lambda c: c.sort_key)
        best_choice = QualityChoice(
            label="Best Quality",
            resolution=best.resolution,
            fps=best.fps,
            container=best.container,
            stream_type=best.stream_type,
            estimated_size_bytes=best.estimated_size_bytes,
            size_is_approximate=best.size_is_approximate,
            video_format=best.video_format,
            audio_format=best.audio_format,
            requires_merge=best.requires_merge,
            is_best_quality=True,
            vcodec=best.vcodec,
            acodec=best.acodec,
            sort_key=9999.0,
        )
        choices.insert(0, best_choice)

    # Audio Only option.
    if best_audio is not None:
        audio_size = best_audio.best_known_size
        if audio_size is None:
            audio_size = best_audio.estimate_size_from_bitrate(duration_seconds)
        audio_choice = QualityChoice(
            label="Audio Only",
            resolution=None,
            fps=None,
            container=best_audio.ext.upper() if best_audio.ext else "M4A",
            stream_type=StreamType.AUDIO_ONLY,
            estimated_size_bytes=audio_size,
            size_is_approximate=best_audio.filesize is None,
            video_format=None,
            audio_format=best_audio,
            requires_merge=False,
            is_audio_only=True,
            acodec=best_audio.acodec,
            sort_key=-1.0,
        )
        choices.append(audio_choice)

    return choices


# Quality ladder offered for playlist downloads. Unlike single-video
# analysis, we deliberately do NOT fetch every playlist video's full format
# list up front (one extra network round-trip per video would make large
# playlists unusably slow to "analyze"). Instead each entry gets a generic
# yt-dlp selector expression that is resolved against that video's own
# formats at download time.
_PLAYLIST_QUALITY_LADDER = [2160, 1440, 1080, 720, 480, 360, 240, 144]


def build_playlist_quality_choices() -> List[QualityChoice]:
    choices: List[QualityChoice] = []

    best_choice = QualityChoice(
        label="Best Quality",
        resolution=None,
        fps=None,
        container="MP4",
        stream_type=StreamType.VIDEO_AND_AUDIO,
        estimated_size_bytes=None,
        size_is_approximate=True,
        video_format=None,
        audio_format=None,
        requires_merge=True,
        is_best_quality=True,
        raw_selector="bestvideo+bestaudio/best",
        sort_key=9999.0,
    )
    choices.append(best_choice)

    for bucket in _PLAYLIST_QUALITY_LADDER:
        choices.append(
            QualityChoice(
                label=f"{bucket}p",
                resolution=None,
                fps=None,
                container="MP4",
                stream_type=StreamType.VIDEO_AND_AUDIO,
                estimated_size_bytes=None,
                size_is_approximate=True,
                video_format=None,
                audio_format=None,
                requires_merge=True,
                raw_selector=f"bestvideo[height<={bucket}]+bestaudio/best[height<={bucket}]",
                sort_key=float(bucket),
            )
        )

    choices.append(
        QualityChoice(
            label="Audio Only",
            resolution=None,
            fps=None,
            container="M4A",
            stream_type=StreamType.AUDIO_ONLY,
            estimated_size_bytes=None,
            size_is_approximate=True,
            video_format=None,
            audio_format=None,
            requires_merge=False,
            is_audio_only=True,
            raw_selector="bestaudio/best",
            sort_key=-1.0,
        )
    )

    return choices


def get_generic_quality_by_label(label: str) -> Optional[QualityChoice]:
    """Look up a generic (selector-based) QualityChoice by its label, e.g.
    to rebuild a quality choice for retrying a failed download from History
    where we only stored the label string, not the original FormatOption
    objects (those aren't persisted -- they're only valid for the video
    session they were fetched in)."""
    for choice in build_playlist_quality_choices():
        if choice.label == label:
            return choice
    return None
