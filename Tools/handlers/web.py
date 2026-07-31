from __future__ import annotations

import re
from datetime import datetime

from Tools.handlers.base import LogEntry

_WEB_LOG = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) "
    r"\[(?P<thread>[^\]]+)\]\s+(?P<level>\w+)\s+"
    r"(?P<source>.*?)\s+\[[^\]]*\]\s+<[^>]*>\s+-\s+(?P<message>.*)$"
)
_WEB_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) ")


class WebHandler:
    name = "web"

    def detect(self, sample_lines: list[str]) -> bool:
        return any(_WEB_LOG.match(line) for line in sample_lines)

    def is_record_start(self, line: str) -> bool:
        return _WEB_TIME.match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        match = _WEB_TIME.match(line)
        if not match:
            return None
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f")

    def parse_line(self, line: str) -> LogEntry | None:
        match = _WEB_LOG.match(line)
        if not match:
            return None
        data = match.groupdict()
        return LogEntry(
            log_type=self.name,
            timestamp=datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S,%f"),
            level=data["level"],
            source=data["source"].strip(),
            thread=data["thread"],
            message=data["message"].strip(),
            raw=line,
        )
