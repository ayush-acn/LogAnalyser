from __future__ import annotations

from datetime import datetime

from Tools.handlers.base import LogEntry


class RawHandler:
    """Fallback: every non-empty line is a record. Never fails detection."""

    name = "raw"

    def detect(self, sample_lines: list[str]) -> bool:
        return True

    def is_record_start(self, line: str) -> bool:
        return bool(line.strip())

    def peek_timestamp(self, line: str) -> datetime | None:
        return None

    def parse_line(self, line: str) -> LogEntry | None:
        if not line.strip():
            return None
        return LogEntry(
            log_type=self.name,
            timestamp=None,
            level=None,
            message=line.rstrip(),
            raw=line,
        )
