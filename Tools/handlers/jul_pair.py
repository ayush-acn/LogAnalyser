from __future__ import annotations

import re
from datetime import datetime

from Tools.handlers.base import LogEntry

# Jul 30, 2026 5:37:56 AM org.glassfish...
_JUL_HEADER = re.compile(
    r"^(?P<time>[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M)\s+"
    r"(?P<source>.+)$"
)
_JUL_LEVEL = re.compile(r"^(?P<level>SEVERE|WARNING|INFO|CONFIG|FINE|FINER|FINEST):\s*(?P<message>.*)$")
_SLF4J = re.compile(r"^SLF4J:\s*(?P<message>.*)$")


class JulPairHandler:
    name = "jul_pair"

    def detect(self, sample_lines: list[str]) -> bool:
        return any(_JUL_HEADER.match(line) or _SLF4J.match(line) for line in sample_lines)

    def is_record_start(self, line: str) -> bool:
        return _JUL_HEADER.match(line) is not None or _SLF4J.match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        match = _JUL_HEADER.match(line)
        if not match:
            return None
        return datetime.strptime(match.group("time"), "%b %d, %Y %I:%M:%S %p")

    def parse_line(self, line: str) -> LogEntry | None:
        slf = _SLF4J.match(line)
        if slf:
            return LogEntry(
                log_type=self.name,
                timestamp=None,
                level="WARN",
                message=slf.group("message").strip(),
                raw=line,
            )
        match = _JUL_HEADER.match(line)
        if not match:
            return None
        return LogEntry(
            log_type=self.name,
            timestamp=self.peek_timestamp(line),
            level=None,
            source=match.group("source").strip(),
            message=match.group("source").strip(),
            raw=line,
        )
