from __future__ import annotations

import re
from datetime import datetime

from Tools.handlers.base import LogEntry

_GC = re.compile(
    r"^\[(?P<time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{4})\]"
    r"\[(?P<uptime>[^\]]+)\]\s*(?P<message>.*)$"
)


class JvmGcHandler:
    name = "jvm_gc"

    def detect(self, sample_lines: list[str]) -> bool:
        return any(_GC.match(line) for line in sample_lines)

    def is_record_start(self, line: str) -> bool:
        return _GC.match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        match = _GC.match(line)
        if not match:
            return None
        raw = match.group("time")
        # 2026-07-30T05:36:51.823+0000
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").replace(tzinfo=None)

    def parse_line(self, line: str) -> LogEntry | None:
        match = _GC.match(line)
        if not match:
            return None
        return LogEntry(
            log_type=self.name,
            timestamp=self.peek_timestamp(line),
            level=None,
            message=match.group("message").strip() or line,
            raw=line,
            details=[f"uptime={match.group('uptime')}"],
        )
