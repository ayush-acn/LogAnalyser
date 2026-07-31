from __future__ import annotations

import re
from datetime import datetime

from Tools.handlers.base import LogEntry

_DC_LOG = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>\w+)\s+-\s+(?P<source>\S+)\s+-\s+(?P<message>.*)$"
)
_DC_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\w+\s+-")


class DeploymentCentreHandler:
    name = "deploymentcentre"

    def detect(self, sample_lines: list[str]) -> bool:
        return any(_DC_LOG.match(line) for line in sample_lines)

    def is_record_start(self, line: str) -> bool:
        return _DC_TIME.match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        match = _DC_TIME.match(line)
        if not match:
            return None
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")

    def parse_line(self, line: str) -> LogEntry | None:
        match = _DC_LOG.match(line)
        if not match:
            return None
        data = match.groupdict()
        return LogEntry(
            log_type=self.name,
            timestamp=datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S"),
            level=data["level"],
            source=data["source"],
            message=data["message"].strip(),
            raw=line,
        )
