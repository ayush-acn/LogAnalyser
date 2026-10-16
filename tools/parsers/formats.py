"""Parsers for each log format this project understands.

A parser does four things:
- decide whether a file is this format
- decide whether a line starts a new log entry
- read the timestamp, when there is one
- pull out the message and any extra fields

Lines that follow an entry, such as a stack trace, are attached later by the reader.
"""

from __future__ import annotations

import re
from datetime import datetime

from tools.parsers.base import LogEntry, PatternHandler

# Example: 2026-07-30 07:06:34,123 [http-1] INFO com.app.Web [req] <user> - started
_WEB_LOG = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) "
    r"\[(?P<thread>[^\]]+)\]\s+(?P<level>\w+)\s+"
    r"(?P<source>.*?)\s+\[[^\]]*\]\s+<[^>]*>\s+-\s+(?P<message>.*)$"
)
_WEB_START = re.compile(r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) ")

# Example: INFO - 2026/07/30-07:06:34,123 UTC - host - source - message
_POOL_LOG = re.compile(
    r"^(?P<level>\w+)\s+-\s+"
    r"(?P<time>\d{4}/\d{2}/\d{2}-\d{2}:\d{2}:\d{2},\d{3}) UTC - "
    r"(?P<host>.*?) - (?P<source>.*?)\s+-\s+(?P<message>.*)$"
)
_POOL_START = re.compile(
    r"^\w+\s+-\s+(?P<time>\d{4}/\d{2}/\d{2}-\d{2}:\d{2}:\d{2},\d{3}) UTC - "
)

# Example: [2026-07-30T05:36:51.823+0000][0.123s] GC pause
_GC_LOG = re.compile(
    r"^\[(?P<time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{4})\]"
    r"\[(?P<uptime>[^\]]+)\]\s*(?P<message>.*)$"
)

# Example: [2026-07-30 07:06:34] [INFO] [1234] service started
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

# Example: 2026-07-30 07:06:34 INFO - com.app.Deploy - deployed
_DC_LOG = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>\w+)\s+-\s+(?P<source>\S+)\s+-\s+(?P<message>.*)$"
)
_DC_START = re.compile(r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\w+\s+-")

# Example: INFO 2026-07-30 07:06:34,123 - client opened
_RAC_LOG = re.compile(
    r"^(?P<level>\w+)\s+"
    r"(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+-\s+"
    r"(?P<message>.*)$"
)
_RAC_START = re.compile(r"^\w+\s+(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+-")

# Example: [0ed8:0001][2026-07-30T07:06:34] Warning: low memory
_VS_LOG = re.compile(
    r"^\[(?P<tid>[^\]]+)\]\[(?P<time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\]\s*"
    r"(?P<message>.*)$"
)
# Example: [7/23/2026, 5:35:22] starting
_VS_BOOT = re.compile(
    r"^\[(?P<time>\d{1,2}/\d{1,2}/\d{4},\s+\d{1,2}:\d{2}:\d{2})\]\s*"
    r"(?P<message>.*)$"
)

# Example: Jul 30, 2026 5:37:56 AM org.glassfish.Main
_JUL_HEADER = re.compile(
    r"^(?P<time>[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M)\s+"
    r"(?P<source>.+)$"
)
_SLF4J = re.compile(r"^SLF4J:\s*(?P<message>.*)$")

# Example: 2026/07/30-07:06:34.123 UTC - INFO - logger - message
_TC_START = re.compile(r"^(?P<time>\d{4}/\d{2}/\d{2}-\d{2}:\d{2}:\d{2}[.,]\d{3}) UTC\b")
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
    return datetime.strptime(raw.replace(",", "."), "%Y/%m/%d-%H:%M:%S.%f")


def _split_tc_rest(rest: str) -> tuple[str | None, str | None, str | None, str]:
    """Split the middle of a Teamcenter line. The last field is the message."""
    parts = [part.strip() for part in rest.split(" - ")]
    if len(parts) == 1:
        parts = [part.strip() for part in rest.split("-")]
        parts = [part for part in parts if part != ""]
        if len(parts) <= 1:
            return None, None, None, rest.strip()
        message = parts[-1]
        return (parts[0] if parts else None), None, None, message

    message = parts[-1]
    middle = [part for part in parts[:-1] if part and part != "-"]
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


class WebHandler(PatternHandler):
    name = "web"
    pattern = _WEB_LOG
    start_pattern = _WEB_START
    time_format = "%Y-%m-%d %H:%M:%S,%f"

    def parse_line(self, line: str) -> LogEntry | None:
        match = self.pattern.match(line)
        if not match:
            return None
        data = match.groupdict()
        return LogEntry(
            log_type=self.name,
            timestamp=self.parse_time(data["time"]),
            level=data["level"],
            source=data["source"].strip(),
            thread=data["thread"],
            message=data["message"].strip(),
            raw=line,
        )


class PoolHandler(PatternHandler):
    name = "pool"
    pattern = _POOL_LOG
    start_pattern = _POOL_START
    time_format = "%Y/%m/%d-%H:%M:%S,%f"

    def parse_line(self, line: str) -> LogEntry | None:
        match = self.pattern.match(line)
        if not match:
            return None
        data = match.groupdict()
        return LogEntry(
            log_type=self.name,
            timestamp=self.parse_time(data["time"]),
            level=data["level"],
            source=data["source"].strip(),
            host=data["host"].strip(),
            message=data["message"].strip(),
            raw=line,
        )


class JvmGcHandler(PatternHandler):
    name = "jvm_gc"
    pattern = _GC_LOG

    def parse_time(self, raw: str) -> datetime:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z").replace(tzinfo=None)

    def parse_line(self, line: str) -> LogEntry | None:
        match = self.pattern.match(line)
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


class DeploymentCentreHandler(PatternHandler):
    name = "deploymentcentre"
    pattern = _DC_LOG
    start_pattern = _DC_START
    time_format = "%Y-%m-%d %H:%M:%S"

    def parse_line(self, line: str) -> LogEntry | None:
        match = self.pattern.match(line)
        if not match:
            return None
        data = match.groupdict()
        return LogEntry(
            log_type=self.name,
            timestamp=self.parse_time(data["time"]),
            level=data["level"],
            source=data["source"],
            message=data["message"].strip(),
            raw=line,
        )


class RacHandler(PatternHandler):
    name = "rac"
    pattern = _RAC_LOG
    start_pattern = _RAC_START
    time_format = "%Y-%m-%d %H:%M:%S,%f"

    def parse_line(self, line: str) -> LogEntry | None:
        match = self.pattern.match(line)
        if not match:
            return None
        return LogEntry(
            log_type=self.name,
            timestamp=self.parse_time(match.group("time")),
            level=match.group("level"),
            message=match.group("message").strip(),
            raw=line,
        )


class VsBracketHandler:
    name = "vs_bracket"

    def detect(self, sample_lines: list[str]) -> bool:
        return any(_VS_LOG.match(line) or _VS_BOOT.match(line) for line in sample_lines)

    def is_record_start(self, line: str) -> bool:
        return _VS_LOG.match(line) is not None or _VS_BOOT.match(line) is not None

    def peek_timestamp(self, line: str) -> datetime | None:
        match = _VS_LOG.match(line)
        if match:
            return datetime.strptime(match.group("time"), "%Y-%m-%dT%H:%M:%S")
        match = _VS_BOOT.match(line)
        if match:
            return datetime.strptime(match.group("time"), "%m/%d/%Y, %H:%M:%S")
        return None

    def parse_line(self, line: str) -> LogEntry | None:
        match = _VS_LOG.match(line)
        if match:
            message = match.group("message").strip()
            level = "WARN" if message.lower().startswith("warning:") else None
            return LogEntry(
                log_type=self.name,
                timestamp=datetime.strptime(match.group("time"), "%Y-%m-%dT%H:%M:%S"),
                level=level,
                thread=match.group("tid"),
                message=message,
                raw=line,
            )
        match = _VS_BOOT.match(line)
        if match:
            return LogEntry(
                log_type=self.name,
                timestamp=datetime.strptime(match.group("time"), "%m/%d/%Y, %H:%M:%S"),
                level=None,
                message=match.group("message").strip(),
                raw=line,
            )
        return None


class JulPairHandler:
    """Java logging. The header is the entry; the following level line is a detail."""

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
        source = match.group("source").strip()
        return LogEntry(
            log_type=self.name,
            timestamp=self.peek_timestamp(line),
            level=None,
            source=source,
            message=source,
            raw=line,
        )


class TcMldHandler:
    """Teamcenter service logs. The timestamp comes first and ends with UTC."""

    name = "tc_mld"

    def detect(self, sample_lines: list[str]) -> bool:
        return any(_TC_START.match(line) for line in sample_lines)

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
        if match:
            source, thread, host, message = _split_tc_rest(match.group("rest"))
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

        if _TC_START.match(line):
            return LogEntry(
                log_type=self.name,
                timestamp=self.peek_timestamp(line),
                level=None,
                message=line[line.find("UTC") + 3 :].lstrip(" -"),
                raw=line,
            )
        return None


class UtilityBannerHandler:
    """Console output with banner lines, such as preferences_manager."""

    name = "utility_banner"

    def detect(self, sample_lines: list[str]) -> bool:
        non_empty = [line for line in sample_lines if line.strip()]
        if len(non_empty) < 2:
            return False
        bannerish = sum(
            1
            for line in non_empty
            if line.strip().startswith("*")
            or "utility" in line.lower()
            or "preferences_manager" in line.lower()
        )
        return bannerish >= 1

    def is_record_start(self, line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith("*") or stripped.startswith("preferences_manager")

    def peek_timestamp(self, line: str) -> datetime | None:
        return None

    def parse_line(self, line: str) -> LogEntry | None:
        if not line.strip() or not self.is_record_start(line):
            return None
        return LogEntry(
            log_type=self.name,
            timestamp=None,
            level=None,
            message=line.strip(),
            raw=line,
        )


class RawHandler:
    """Last resort. Every non-empty line is its own entry."""

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
