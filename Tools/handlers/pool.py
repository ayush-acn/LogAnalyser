from __future__ import annotations

import re
from datetime import datetime

from Tools.handlers.base import LogEntry

_POOL_LOG = re.compile(
    r"^(?P<level>\w+)\s+-\s+"
    r"(?P<time>\d{4}/\d{2}/\d{2}-\d{2}:\d{2}:\d{2},\d{3}) UTC - "
    r"(?P<host>.*?) - (?P<source>.*?)\s+-\s+(?P<message>.*)$"
)
_POOL_TIME = re.compile(
    r"^\w+\s+-\s+(\d{4}/\d{2}/\d{2}-\d{2}:\d{2}:\d{2},\d{3}) UTC - "
)


class PoolHandler:
    name = "pool"

    def detect(self, sample_lines: list[str]) -> bool:
        return any(_POOL_LOG.match(line) for line in sample_lines)

    def is_record_start(self, line: str) -> bool:
        return _POOL_TIME.match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        match = _POOL_TIME.match(line)
        if not match:
            return None
        return datetime.strptime(match.group(1), "%Y/%m/%d-%H:%M:%S,%f")

    def parse_line(self, line: str) -> LogEntry | None:
        match = _POOL_LOG.match(line)
        if not match:
            return None
        data = match.groupdict()
        return LogEntry(
            log_type=self.name,
            timestamp=datetime.strptime(data["time"], "%Y/%m/%d-%H:%M:%S,%f"),
            level=data["level"],
            source=data["source"].strip(),
            host=data["host"].strip(),
            message=data["message"].strip(),
            raw=line,
        )
