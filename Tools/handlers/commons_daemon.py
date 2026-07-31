from __future__ import annotations

import re
from datetime import datetime

from Tools.handlers.base import LogEntry

_PROCRUN = re.compile(
    r"^\[(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+"
    r"\[(?P<level>\w+)\]\s+"
    r"\[(?P<pid>\s*\d+)\]\s*"
    r"(?P<message>.*)$"
)
_DAEMON_PLAIN = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<message>Commons Daemon.*)$"
)


class CommonsDaemonHandler:
    name = "commons_daemon"

    def detect(self, sample_lines: list[str]) -> bool:
        return any(_PROCRUN.match(line) or _DAEMON_PLAIN.match(line) for line in sample_lines)

    def is_record_start(self, line: str) -> bool:
        return _PROCRUN.match(line) is not None or _DAEMON_PLAIN.match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        for pattern in (_PROCRUN, _DAEMON_PLAIN):
            match = pattern.match(line)
            if match:
                return datetime.strptime(match.group("time"), "%Y-%m-%d %H:%M:%S")
        return None

    def parse_line(self, line: str) -> LogEntry | None:
        match = _PROCRUN.match(line)
        if match:
            return LogEntry(
                log_type=self.name,
                timestamp=datetime.strptime(match.group("time"), "%Y-%m-%d %H:%M:%S"),
                level=match.group("level"),
                host=match.group("pid").strip(),
                message=match.group("message").strip(),
                raw=line,
            )
        plain = _DAEMON_PLAIN.match(line)
        if plain:
            return LogEntry(
                log_type=self.name,
                timestamp=datetime.strptime(plain.group("time"), "%Y-%m-%d %H:%M:%S"),
                level="INFO",
                message=plain.group("message").strip(),
                raw=line,
            )
        return None
