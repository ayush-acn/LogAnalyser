from __future__ import annotations

import re
from datetime import datetime

from Tools.handlers.base import LogEntry

# [0ed8:0001][2026-07-30T07:06:34] Warning: ...
_VS_DD = re.compile(
    r"^\[(?P<tid>[^\]]+)\]\[(?P<time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\]\s*"
    r"(?P<message>.*)$"
)
# [7/23/2026, 5:35:22] message
_VS_BOOT = re.compile(
    r"^\[(?P<time>\d{1,2}/\d{1,2}/\d{4},\s+\d{1,2}:\d{2}:\d{2})\]\s*"
    r"(?P<message>.*)$"
)


class VsBracketHandler:
    name = "vs_bracket"

    def detect(self, sample_lines: list[str]) -> bool:
        return any(_VS_DD.match(line) or _VS_BOOT.match(line) for line in sample_lines)

    def is_record_start(self, line: str) -> bool:
        return _VS_DD.match(line) is not None or _VS_BOOT.match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        dd = _VS_DD.match(line)
        if dd:
            return datetime.strptime(dd.group("time"), "%Y-%m-%dT%H:%M:%S")
        boot = _VS_BOOT.match(line)
        if boot:
            return datetime.strptime(boot.group("time"), "%m/%d/%Y, %H:%M:%S")
        return None

    def parse_line(self, line: str) -> LogEntry | None:
        dd = _VS_DD.match(line)
        if dd:
            message = dd.group("message").strip()
            level = None
            if message.lower().startswith("warning:"):
                level = "WARN"
            return LogEntry(
                log_type=self.name,
                timestamp=datetime.strptime(dd.group("time"), "%Y-%m-%dT%H:%M:%S"),
                level=level,
                thread=dd.group("tid"),
                message=message,
                raw=line,
            )
        boot = _VS_BOOT.match(line)
        if boot:
            return LogEntry(
                log_type=self.name,
                timestamp=datetime.strptime(boot.group("time"), "%m/%d/%Y, %H:%M:%S"),
                level=None,
                message=boot.group("message").strip(),
                raw=line,
            )
        return None
