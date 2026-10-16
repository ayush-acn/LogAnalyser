"""Path, time, and level helpers used by the three log tools."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from tools.access import resolve_allowed_file
from tools.discovery import resolve_log_group

TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def parse_time(value: str | None) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip().replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    text = re.sub(r"[+-]\d{2}:?\d{2}$", "", text).strip()
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised time {value!r}. Use YYYY-MM-DD HH:MM:SS.")


def open_log_group(file_path: str) -> tuple[list[Path], str | None]:
    try:
        path = resolve_allowed_file(file_path)
    except (OSError, ValueError) as exc:
        return [], str(exc)
    group = resolve_log_group(path)
    return (group or [path]), None


def parse_levels(levels: str | None) -> set[str] | None:
    if levels is None or not str(levels).strip():
        return None
    parsed = {part.strip().upper() for part in str(levels).split(",") if part.strip()}
    return parsed or None
