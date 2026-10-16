from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class LogEntry:
    """One log event after it has been parsed."""

    log_type: str
    timestamp: datetime | None
    level: str | None
    message: str
    raw: str
    source: str | None = None
    host: str | None = None
    thread: str | None = None
    details: list[str] | None = None
    file_path: str | None = None
    line_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Fields returned to the AI. The full raw line is left out on purpose."""
        data: dict[str, Any] = {
            "file_path": self.file_path,
            "line_number": self.line_number,
        }
        if self.timestamp is not None:
            data["timestamp"] = self.timestamp.isoformat(sep=" ")
        if self.level:
            data["level"] = self.level
        if self.source:
            data["source"] = self.source
        if self.host:
            data["host"] = self.host
        if self.thread:
            data["thread"] = self.thread
        data["message"] = self.message
        if self.details:
            data["details"] = list(self.details)
        if self.log_type:
            data["log_type"] = self.log_type
        return data


@runtime_checkable
class FormatHandler(Protocol):
    """What every log format must be able to do."""

    name: str

    def detect(self, sample_lines: list[str]) -> bool:
        ...

    def is_record_start(self, line: str) -> bool:
        ...

    def parse_line(self, line: str) -> LogEntry | None:
        ...

    def peek_timestamp(self, line: str) -> datetime | None:
        ...


class PatternHandler:
    """Shared code for formats that are recognized by a regular expression.

    `pattern` must match a full record. `start_pattern` is optional and is used
    when a looser line should still count as the start of a record.
    Both patterns should name the timestamp group `time` when the line has one.
    """

    name: str
    pattern: re.Pattern[str]
    start_pattern: re.Pattern[str] | None = None
    time_format: str = ""

    def _start_pattern(self) -> re.Pattern[str]:
        return self.start_pattern or self.pattern

    def detect(self, sample_lines: list[str]) -> bool:
        return any(self.pattern.match(line) for line in sample_lines)

    def is_record_start(self, line: str) -> bool:
        return self._start_pattern().match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        match = self._start_pattern().match(line)
        if not match:
            return None
        raw = match.groupdict().get("time")
        if not raw:
            return None
        return self.parse_time(raw)

    def parse_time(self, raw: str) -> datetime:
        return datetime.strptime(raw, self.time_format)

    def parse_line(self, line: str) -> LogEntry | None:
        raise NotImplementedError
