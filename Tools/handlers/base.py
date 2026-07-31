from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class LogEntry:
    log_type: str
    timestamp: datetime | None
    level: str | None
    message: str
    raw: str
    source: str | None = None
    host: str | None = None
    thread: str | None = None
    details: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat(sep=" ") if self.timestamp else None
        return data


@runtime_checkable
class FormatHandler(Protocol):
    name: str

    def detect(self, sample_lines: list[str]) -> bool:
        ...

    def is_record_start(self, line: str) -> bool:
        ...

    def parse_line(self, line: str) -> LogEntry | None:
        ...

    def peek_timestamp(self, line: str) -> datetime | None:
        ...
