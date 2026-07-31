from __future__ import annotations

import re
from datetime import datetime

from Tools.handlers.base import LogEntry

_RAC = re.compile(
    r"^(?P<level>\w+)\s+"
    r"(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+-\s+"
    r"(?P<message>.*)$"
)
_RAC_TIME = re.compile(r"^\w+\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+-")


class RacHandler:
    name = "rac"

    def detect(self, sample_lines: list[str]) -> bool:
        return any(_RAC.match(line) for line in sample_lines)

    def is_record_start(self, line: str) -> bool:
        return _RAC_TIME.match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        match = _RAC_TIME.match(line)
        if not match:
            return None
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f")

    def parse_line(self, line: str) -> LogEntry | None:
        match = _RAC.match(line)
        if not match:
            return None
        return LogEntry(
            log_type=self.name,
            timestamp=datetime.strptime(match.group("time"), "%Y-%m-%d %H:%M:%S,%f"),
            level=match.group("level"),
            message=match.group("message").strip(),
            raw=line,
        )
