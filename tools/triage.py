"""Decide which log entries are problems, and group repeats together."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from tools.parsers.base import LogEntry

PROBLEM_LEVELS = {"FATAL", "CRITICAL", "SEVERE", "ERROR", "WARN", "WARNING"}

_KEYWORDS = (
    "exception",
    "caused by",
    "failed",
    "timed out",
    "refused",
    "outofmemory",
)

_SEVERITY = {
    "FATAL": 5,
    "CRITICAL": 5,
    "SEVERE": 4,
    "ERROR": 4,
    "WARN": 2,
    "WARNING": 2,
}

_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_WIN_PATH = re.compile(r"\b[A-Za-z]:\\[^\s]+")
_UNIX_PATH = re.compile(r"(?:/[\w.-]+){2,}")
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_TIMESTAMP = re.compile(
    r"\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"
)
_HEX = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_NUMBER = re.compile(r"\d+")
_SPACE = re.compile(r"\s+")


@dataclass
class ProblemGroup:
    """One repeated problem, with a single sample entry the model can cite."""

    fingerprint: str
    level: str | None
    count: int
    first_seen: datetime | None
    last_seen: datetime | None
    sample: LogEntry


def is_problem(entry: LogEntry) -> bool:
    """True for warning-or-worse levels, and for level-less lines that look like failures."""
    if entry.level and entry.level.upper() in PROBLEM_LEVELS:
        return True
    text = entry.message or ""
    if entry.details:
        text = text + "\n" + "\n".join(entry.details)
    lowered = text.lower()
    return any(keyword in lowered for keyword in _KEYWORDS)


def normalize_message(message: str) -> str:
    """Strip ids, paths, and numbers so the same failure groups together."""
    text = _QUOTED.sub("<str>", message)
    text = _UUID.sub("<uuid>", text)
    text = _WIN_PATH.sub("<path>", text)
    text = _UNIX_PATH.sub("<path>", text)
    text = _TIMESTAMP.sub("<time>", text)
    text = _HEX.sub("<hex>", text)
    text = _NUMBER.sub("<n>", text)
    return _SPACE.sub(" ", text).strip().lower()


def fingerprint(message: str) -> str:
    """Short stable id for a normalized message."""
    normalized = normalize_message(message)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]


def group_problems(entries: list[LogEntry], limit: int) -> list[ProblemGroup]:
    """Group problem entries. Highest severity, then highest count, come first."""
    grouped: dict[tuple[str, str], ProblemGroup] = {}
    for entry in entries:
        if not is_problem(entry):
            continue
        level = entry.level.upper() if entry.level else None
        key = (level or "", fingerprint(entry.message))
        current = grouped.get(key)
        if current is None:
            grouped[key] = ProblemGroup(
                fingerprint=key[1],
                level=level,
                count=1,
                first_seen=entry.timestamp,
                last_seen=entry.timestamp,
                sample=entry,
            )
            continue
        current.count += 1
        current.sample = entry
        if entry.timestamp is not None:
            if current.first_seen is None or entry.timestamp < current.first_seen:
                current.first_seen = entry.timestamp
            if current.last_seen is None or entry.timestamp > current.last_seen:
                current.last_seen = entry.timestamp

    ranked = sorted(
        grouped.values(),
        key=lambda item: (_SEVERITY.get(item.level or "", 1), item.count),
        reverse=True,
    )
    return ranked[: max(0, limit)]
