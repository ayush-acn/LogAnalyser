from __future__ import annotations

import re
from datetime import datetime

from Tools.handlers.base import LogEntry

# Teamcenter MLD / service logs: time-first UTC dash fields.
# Accepts '.' or ',' fractional seconds; optional EVENT / INFO -- variants.
_TC_START = re.compile(
    r"^(?P<time>\d{4}/\d{2}/\d{2}-\d{2}:\d{2}:\d{2}[.,]\d{3}) UTC\b"
)
_TC_LOG = re.compile(
    r"^(?P<time>\d{4}/\d{2}/\d{2}-\d{2}:\d{2}:\d{2}[.,]\d{3}) UTC\s*-\s*"
    r"(?P<level>\w+)\s*-+\s*"
    r"(?P<rest>.*)$"
)
_TC_MLD_INIT = re.compile(
    r"^(?P<time>\d{4}/\d{2}/\d{2}-\d{2}:\d{2}:\d{2}[.,]\d{3}) UTC\s+"
    r"(?P<message>MLD Log init:.*)$"
)


def _parse_tc_time(raw: str) -> datetime:
    normalized = raw.replace(",", ".")
    return datetime.strptime(normalized, "%Y/%m/%d-%H:%M:%S.%f")


def _split_rest(rest: str) -> tuple[str | None, str | None, str | None, str]:
    """
    Best-effort split of dash-separated middle fields into
    (source/logger, thread, host/id leftovers, message).
    """
    parts = [p.strip() for p in rest.split(" - ")]
    if len(parts) == 1:
        # Also try single-dash splits when spacing is irregular.
        parts = [p.strip() for p in rest.split("-")]
        parts = [p for p in parts if p != ""]
        if len(parts) <= 1:
            return None, None, None, rest.strip()
        message = parts[-1]
        return (parts[0] if parts else None), None, None, message

    message = parts[-1]
    middle = [p for p in parts[:-1] if p and p != "-"]
    source = middle[0] if middle else None
    thread = None
    host = None
    for item in middle[1:]:
        if item.lower() in {"main"} or item.startswith("("):
            thread = item.strip("()")
        elif re.fullmatch(r"[0-9A-Fa-f]{8,}", item.replace("R", "")):
            host = item
        elif source is None:
            source = item
        elif host is None:
            host = item
    return source, thread, host, message


class TcMldHandler:
    name = "tc_mld"

    def detect(self, sample_lines: list[str]) -> bool:
        hits = sum(1 for line in sample_lines if _TC_START.match(line))
        return hits >= 1

    def is_record_start(self, line: str) -> bool:
        return _TC_START.match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        match = _TC_START.match(line)
        if not match:
            return None
        return _parse_tc_time(match.group("time"))

    def parse_line(self, line: str) -> LogEntry | None:
        init = _TC_MLD_INIT.match(line)
        if init:
            return LogEntry(
                log_type=self.name,
                timestamp=_parse_tc_time(init.group("time")),
                level="INFO",
                message=init.group("message").strip(),
                raw=line,
            )

        match = _TC_LOG.match(line)
        if not match:
            if _TC_START.match(line):
                # Timestamped but irregular — keep as raw-structured entry.
                ts = self.peek_timestamp(line)
                return LogEntry(
                    log_type=self.name,
                    timestamp=ts,
                    level=None,
                    message=line[line.find("UTC") + 3 :].lstrip(" -"),
                    raw=line,
                )
            return None

        source, thread, host, message = _split_rest(match.group("rest"))
        return LogEntry(
            log_type=self.name,
            timestamp=_parse_tc_time(match.group("time")),
            level=match.group("level"),
            source=source,
            thread=thread,
            host=host,
            message=message.strip(),
            raw=line,
        )
