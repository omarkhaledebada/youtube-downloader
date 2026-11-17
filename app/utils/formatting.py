"""Human-readable formatting helpers for sizes, speeds, and durations."""
from __future__ import annotations

from typing import Optional


def format_bytes(num_bytes: Optional[float]) -> str:
    """Format a byte count as e.g. '853 KB', '14.7 MB', '1.82 GB'."""
    if num_bytes is None or num_bytes < 0:
        return "Unknown"
    value = float(num_bytes)
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    if units[unit_index] == "B":
        return f"{int(value)} B"
    if value >= 100:
        return f"{value:.0f} {units[unit_index]}"
    if value >= 10:
        return f"{value:.1f} {units[unit_index]}"
    return f"{value:.2f} {units[unit_index]}"


def format_size_label(num_bytes: Optional[float], is_approximate: bool) -> str:
    """Return a size label, prefixing '~' when the value is only approximate."""
    if num_bytes is None:
        return "Unknown"
    formatted = format_bytes(num_bytes)
    return f"~{formatted}" if is_approximate else formatted


def format_speed(bytes_per_second: Optional[float]) -> str:
    if not bytes_per_second or bytes_per_second <= 0:
        return "-- MB/s"
    return f"{format_bytes(bytes_per_second)}/s"


def format_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "--"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} sec"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def format_percent(fraction: Optional[float]) -> str:
    if fraction is None:
        return "0%"
    return f"{max(0.0, min(100.0, fraction * 100)):.0f}%"
