import os
import re
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from Tools import DEFAULT_LATEST_LOGS

LogFormat = Literal["web", "pool"]

@dataclass
class LogEntry:
    log_type: str
    timestamp: datetime | None
    level: str | None
    message: str
    raw: str
    source: str | None = None
    host: str | None = None
    thread: str | None = None
    details: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat(sep=" ") if self.timestamp else None
        return data

class LogResources:
    WEB_LOG = re.compile(
        r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) "
        r"\[(?P<thread>[^\]]+)\]\s+(?P<level>\w+)\s+"
        r"(?P<source>.*?)\s+\[[^\]]*\]\s+<[^>]*>\s+-\s+(?P<message>.*)$"
    )
    POOL_LOG = re.compile(
        r"^(?P<level>\w+)\s+-\s+"
        r"(?P<time>\d{4}/\d{2}/\d{2}-\d{2}:\d{2}:\d{2},\d{3}) UTC - "
        r"(?P<host>.*?) - (?P<source>.*?)\s+-\s+(?P<message>.*)$"
    )
    # Cheap timestamp-only peeks (avoid full LogEntry construction out of range).
    WEB_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) ")
    POOL_TIME = re.compile(
        r"^\w+\s+-\s+(\d{4}/\d{2}/\d{2}-\d{2}:\d{2}:\d{2},\d{3}) UTC - "
    )

    def __init__(self):
        self.logs_dir = None
        self.file_name = None
        self.default_latest_count = DEFAULT_LATEST_LOGS
        self._format_cache: dict[str, LogFormat | None] = {}

    def fetch_logs(
        self,
        file_path: Path,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        skip: int = 0,
        n: int = DEFAULT_LATEST_LOGS,
    ) -> list[dict[str, Any]]:
        """
        Returns formatted logs from a file.

        - start_time/end_time: inclusive time range.
        - from_bottom + limit: bottom-based paging, e.g. from_bottom=20, limit=30 gives 20-50.
        - no filters: latest default_latest_count logs.
        """
        if not file_path.is_file():
            raise FileNotFoundError(f"File {file_path} not found")
            
        if start_time or end_time:
            start_time, end_time = self._normalize_time_range(start_time, end_time)
            entries = self._parse_time_range(file_path, start_time, end_time)
        else:
            bottom = skip or 0
            count = n or self.default_latest_count
            entries = self._parse_latest(file_path, count, skip=bottom)

        return [entry.to_dict() for entry in entries]

    def _parse_time_range(
        self,
        file_path: Path,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> list[LogEntry]:
        log_format = self._detect_format(file_path)
        entries: list[LogEntry] = []
        keep_current = False
        start_offset = self._find_time_offset(file_path, start_time, log_format) if start_time else 0

        with open(file_path, "r", encoding="utf-8", errors="replace") as file:
            if start_offset > 0:
                # Offset is always aligned to a line start (after a too-early entry).
                file.seek(start_offset)

            for line in file:
                line = line.rstrip("\n")
                timestamp = self._peek_timestamp(line, log_format)

                if timestamp is not None:
                    if end_time and timestamp > end_time:
                        break

                    in_range = (start_time is None or timestamp >= start_time) and (
                        end_time is None or timestamp <= end_time
                    )
                    keep_current = in_range
                    if in_range:
                        entry = self._parse_line(line, log_format)
                        if entry:
                            entries.append(entry)
                    continue

                if keep_current and entries:
                    self._append_detail(entries[-1], line)

        return entries

    def _parse_latest(
        self,
        file_path: Path,
        entry_count: int,
        skip: int = 0,
    ) -> list[LogEntry]:
        needed = skip + entry_count
        if entry_count <= 0 or needed <= 0:
            return []

        log_format = self._detect_format(file_path)
        # Tail covers skip+count starts; only materialize the older page entries.
        lines = self._read_tail_lines(file_path, needed, log_format)
        return self._parse_lines(lines, log_format, max_entries=entry_count, keep="first")

    def _read_tail_lines(
        self,
        file_path: Path,
        entry_count: int,
        log_format: LogFormat | None = None,
        chunk_size: int = 16 * 1024,
    ) -> list[str]:
        """
        Read the smallest tail that contains at least `entry_count` log starts,
        then trim to the exact window starting at the Nth-from-last start.
        """
        if log_format is None:
            log_format = self._detect_format(file_path)

        buffer = b""
        with open(file_path, "rb") as file:
            file.seek(0, 2)
            position = file.tell()

            while position > 0:
                read_size = min(chunk_size, position)
                position -= read_size
                file.seek(position)
                buffer = file.read(read_size) + buffer

                text = buffer.decode("utf-8", errors="replace")
                # If we did not start at EOF beginning, first line may be partial.
                lines = text.splitlines()
                start_indexes = self._log_start_indexes(lines, log_format)
                if len(start_indexes) >= entry_count:
                    # Trim to exact window so callers never parse overshoot.
                    trim_at = start_indexes[-entry_count]
                    return lines[trim_at:]

        lines = buffer.decode("utf-8", errors="replace").splitlines()
        start_indexes = self._log_start_indexes(lines, log_format)
        if not start_indexes:
            return []
        if len(start_indexes) >= entry_count:
            return lines[start_indexes[-entry_count] :]
        # Incomplete leading fragment (mid-line seek) — drop until first real start.
        return lines[start_indexes[0] :]

    def _parse_lines(
        self,
        lines: list[str],
        log_format: LogFormat | None = None,
        max_entries: int | None = None,
        keep: Literal["first", "last"] = "last",
    ) -> list[LogEntry]:
        if max_entries is not None and max_entries <= 0:
            return []

        if max_entries is None:
            entries: list[LogEntry] | deque[LogEntry] = []
            stop_after_first = False
        elif keep == "first":
            entries = []
            stop_after_first = True
        else:
            entries = deque(maxlen=max_entries)
            stop_after_first = False

        for line in lines:
            entry = self._parse_line(line, log_format)
            if entry:
                if stop_after_first and len(entries) >= max_entries:
                    break
                entries.append(entry)
            elif entries:
                self._append_detail(entries[-1], line)

        return list(entries)

    def _log_start_indexes(
        self,
        lines: list[str],
        log_format: LogFormat | None,
    ) -> list[int]:
        return [i for i, line in enumerate(lines) if self._is_log_start(line, log_format)]

    def _is_log_start(self, line: str, log_format: LogFormat | None = None) -> bool:
        if log_format == "web":
            return self.WEB_TIME.match(line) is not None
        if log_format == "pool":
            return self.POOL_TIME.match(line) is not None
        return self.WEB_TIME.match(line) is not None or self.POOL_TIME.match(line) is not None

    def _detect_format(self, file_path: Path | str) -> LogFormat | None:
        key = str(file_path)
        if key in self._format_cache:
            return self._format_cache[key]

        detected: LogFormat | None = None
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as file:
                for _ in range(200):
                    line = file.readline()
                    if not line:
                        break
                    line = line.rstrip("\n")
                    if self.WEB_LOG.match(line):
                        detected = "web"
                        break
                    if self.POOL_LOG.match(line):
                        detected = "pool"
                        break
        except OSError:
            detected = None

        self._format_cache[key] = detected
        return detected

    def _find_time_offset(
        self,
        file_path: Path,
        start_time: datetime,
        log_format: LogFormat | None,
    ) -> int:
        """
        Binary-search a byte offset at/before the first log with timestamp >= start_time.
        Returns 0 if the file is small or search is inconclusive.
        """
        size = file_path.stat().st_size
        if size < 64 * 1024:
            return 0

        low, high = 0, size
        best = 0

        with open(file_path, "rb") as file:
            for _ in range(64):
                if high - low < 256:
                    break
                mid = (low + high) // 2
                file.seek(mid)
                if mid > 0:
                    file.readline()  # discard partial line

                timestamp = None
                for _ in range(50):
                    raw = file.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", errors="replace").rstrip("\n")
                    timestamp = self._peek_timestamp(line, log_format)
                    if timestamp is not None:
                        break

                if timestamp is None:
                    # No log header nearby — search earlier.
                    high = mid
                    continue

                if timestamp < start_time:
                    # Safe to skip everything through this too-early entry.
                    low = file.tell()
                    best = low
                else:
                    high = mid

        return max(0, best)

    def _normalize_time_range(
        self,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> tuple[datetime | None, datetime | None]:
        # Strip timezone info to match log file timestamps (which are naive)
        if start_time and start_time.tzinfo is not None:
            start_time = start_time.replace(tzinfo=None)
        if end_time and end_time.tzinfo is not None:
            end_time = end_time.replace(tzinfo=None)
        
        if start_time and end_time and start_time > end_time:
            return end_time, start_time
        return start_time, end_time

    def _is_in_time_range(
        self,
        entry: LogEntry,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> bool:
        # Strip timezone info to match log file timestamps (which are naive)
        if start_time and start_time.tzinfo is not None:
            start_time = start_time.replace(tzinfo=None)
        if end_time and end_time.tzinfo is not None:
            end_time = end_time.replace(tzinfo=None)
        
        # Boundaries are inclusive: start_time <= log timestamp <= end_time.
        return bool(
            entry.timestamp
            and (start_time is None or entry.timestamp >= start_time)
            and (end_time is None or entry.timestamp <= end_time)
        )

    def _peek_timestamp(
        self,
        line: str,
        log_format: LogFormat | None = None,
    ) -> datetime | None:
        if log_format == "web" or log_format is None:
            match = self.WEB_TIME.match(line)
            if match:
                return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f")
            if log_format == "web":
                return None

        if log_format == "pool" or log_format is None:
            match = self.POOL_TIME.match(line)
            if match:
                return datetime.strptime(match.group(1), "%Y/%m/%d-%H:%M:%S,%f")

        return None

    def _append_detail(self, entry: LogEntry, line: str) -> None:
        entry.raw += "\n" + line
        if entry.details is None:
            entry.details = [line]
        else:
            entry.details.append(line)

    def _parse_line(
        self,
        line: str,
        log_format: LogFormat | None = None,
    ) -> LogEntry | None:
        if log_format == "web":
            return self._parse_web_line(line)
        if log_format == "pool":
            return self._parse_pool_line(line)

        return self._parse_web_line(line) or self._parse_pool_line(line)

    def _parse_web_line(self, line: str) -> LogEntry | None:
        web_match = self.WEB_LOG.match(line)
        if not web_match:
            return None
        data = web_match.groupdict()
        return LogEntry(
            log_type="web",
            timestamp=datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S,%f"),
            level=data["level"],
            source=data["source"].strip(),
            thread=data["thread"],
            message=data["message"].strip(),
            raw=line,
        )

    def _parse_pool_line(self, line: str) -> LogEntry | None:
        pool_match = self.POOL_LOG.match(line)
        if not pool_match:
            return None
        data = pool_match.groupdict()
        return LogEntry(
            log_type="pool",
            timestamp=datetime.strptime(data["time"], "%Y/%m/%d-%H:%M:%S,%f"),
            level=data["level"],
            source=data["source"].strip(),
            host=data["host"].strip(),
            message=data["message"].strip(),
            raw=line,
        )


def get_logs_root(project_root: str | Path) -> Path:
    return Path(project_root) / "logs"


def detect_log_type(log_file: Path) -> str:
    with open(log_file, "r", encoding="utf-8", errors="replace") as file:
        for _ in range(200):
            line = file.readline()
            if not line:
                break
            stripped = line.rstrip("\n")
            if LogResources.WEB_LOG.match(stripped):
                return "web"
            if LogResources.POOL_LOG.match(stripped):
                return "pool"
    return "unknown"


def discover_log_files(logs_root: str | Path) -> list[dict[str, Any]]:
    logs_root = Path(logs_root)
    records: list[dict[str, Any]] = []
    for log_file in sorted(logs_root.rglob("*")):
        if not log_file.is_file():
            continue
        if log_file.suffix.lower() not in {".log", ".txt"}:
            continue
        records.append(
            {
                "label": log_file.name,
                "path": log_file,
                "type": detect_log_type(log_file),
                "folder": log_file.parent.name.lower(),
                "logs_subdir": log_file.parent.relative_to(logs_root).as_posix(),
            }
        )
    return records


def list_log_types(records: list[dict[str, Any]]) -> list[str]:
    return sorted({row["type"] for row in records})


def list_folders(records: list[dict[str, Any]], log_type: str) -> list[str]:
    scoped = records if log_type == "all" else [row for row in records if row["type"] == log_type]
    return sorted({row["folder"] for row in scoped})


def filter_records(
    records: list[dict[str, Any]],
    log_type: str,
    log_folder: str,
) -> list[dict[str, Any]]:
    result = records
    if log_type != "all":
        result = [row for row in result if row["type"] == log_type]
    if log_folder != "all":
        result = [row for row in result if row["folder"] == log_folder]
    return result










if __name__ == "__main__":
    log_resources = LogResources(r"logs\LOGS_POOL_DUMP\PoolServer1")
    # logs = log_resources.fetch_logs_from_file("ServerManager.log")
    # print(logs)
    # print(len(logs))

    # st = '2024/07/14-20:35:34,479 UTC'
    # st = datetime.strptime(st, "%Y/%m/%d-%H:%M:%S,%f UTC")
    # et = '2024/07/15-05:07:19,510 UTC'
    # et = datetime.strptime(et, "%Y/%m/%d-%H:%M:%S,%f UTC")
    # logs = log_resources.fetch_logs_from_file("ServerManager.log", st, et)
    # print(logs)
    # print(len(logs))
    # print(logs[0])

    logs = log_resources.fetch_logs_from_file("ServerManager.log", skip=100, n=30)
    print(logs)
    print(len(logs))
