from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from Tools import DEFAULT_LATEST_LOGS
from Tools.handlers.base import FormatHandler, LogEntry
from Tools.handlers.registry import detect_handler


class LogResources:
    def __init__(self):
        self.logs_dir = None
        self.file_name = None
        self.default_latest_count = DEFAULT_LATEST_LOGS
        self._handler_cache: dict[str, FormatHandler] = {}

    def fetch_logs(
        self,
        file_path: Path,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        skip: int = 0,
        n: int = DEFAULT_LATEST_LOGS,
    ) -> list[dict[str, Any]]:
        """
        Returns formatted logs from a file (or merged multi-file path list via
        fetch_logs_from_paths).
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File {path} not found")

        if path.stat().st_size == 0:
            return []

        if start_time or end_time:
            start_time, end_time = self._normalize_time_range(start_time, end_time)
            entries = self._parse_time_range(path, start_time, end_time)
        else:
            count = n or self.default_latest_count
            entries = self._parse_latest(path, count, skip=skip or 0)

        return [entry.to_dict() for entry in entries]

    def fetch_logs_from_paths(
        self,
        paths: list[Path],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        skip: int = 0,
        n: int = DEFAULT_LATEST_LOGS,
    ) -> list[dict[str, Any]]:
        """Parse multiple files in order (already-merged rotation group)."""
        if not paths:
            return []
        if len(paths) == 1:
            return self.fetch_logs(paths[0], start_time=start_time, end_time=end_time, skip=skip, n=n)

        # Parse each file fully for the filter, then apply skip/n on the combined list.
        combined: list[LogEntry] = []
        for path in paths:
            if not path.is_file() or path.stat().st_size == 0:
                continue
            handler = self._detect_handler(path)
            with open(path, "r", encoding="utf-8", errors="replace") as file:
                lines = [line.rstrip("\n") for line in file]
            combined.extend(self._parse_lines(lines, handler))

        if start_time or end_time:
            start_time, end_time = self._normalize_time_range(start_time, end_time)
            combined = [
                entry
                for entry in combined
                if entry.timestamp is None
                or (
                    (start_time is None or entry.timestamp >= start_time)
                    and (end_time is None or entry.timestamp <= end_time)
                )
            ]
            return [entry.to_dict() for entry in combined]

        count = n or self.default_latest_count
        bottom = skip or 0
        if not combined:
            return []
        if bottom:
            end = len(combined) - bottom
            start = max(0, end - count)
            window = combined[start:end] if end > 0 else []
        else:
            window = combined[-count:]
        return [entry.to_dict() for entry in window]

    def _parse_time_range(
        self,
        file_path: Path,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> list[LogEntry]:
        handler = self._detect_handler(file_path)
        entries: list[LogEntry] = []
        keep_current = False
        start_offset = self._find_time_offset(file_path, start_time, handler) if start_time else 0

        with open(file_path, "r", encoding="utf-8", errors="replace") as file:
            if start_offset > 0:
                file.seek(start_offset)

            for line in file:
                line = line.rstrip("\n")
                timestamp = handler.peek_timestamp(line)

                if handler.is_record_start(line):
                    if timestamp is not None:
                        if end_time and timestamp > end_time:
                            break
                        in_range = (start_time is None or timestamp >= start_time) and (
                            end_time is None or timestamp <= end_time
                        )
                        keep_current = in_range
                        if in_range:
                            entry = handler.parse_line(line)
                            if entry:
                                entries.append(entry)
                        continue
                    # Untimestamped record starts: include if no time filter binding.
                    keep_current = start_time is None and end_time is None
                    if keep_current:
                        entry = handler.parse_line(line)
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

        handler = self._detect_handler(file_path)
        # Tail covers skip+count starts; keep="first" yields the older page.
        lines = self._read_tail_lines(file_path, needed, handler)
        return self._parse_lines(lines, handler, max_entries=entry_count, keep="first")

    def _read_tail_lines(
        self,
        file_path: Path,
        entry_count: int,
        handler: FormatHandler,
        chunk_size: int = 16 * 1024,
    ) -> list[str]:
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
                lines = text.splitlines()
                start_indexes = [i for i, line in enumerate(lines) if handler.is_record_start(line)]
                if len(start_indexes) >= entry_count:
                    trim_at = start_indexes[-entry_count]
                    return lines[trim_at:]

        lines = buffer.decode("utf-8", errors="replace").splitlines()
        start_indexes = [i for i, line in enumerate(lines) if handler.is_record_start(line)]
        if not start_indexes:
            # Untimestamped / raw: return whole tail-ish content as lines.
            return lines[-max(entry_count * 4, entry_count) :] if lines else []
        if len(start_indexes) >= entry_count:
            return lines[start_indexes[-entry_count] :]
        return lines[start_indexes[0] :]

    def _parse_lines(
        self,
        lines: list[str],
        handler: FormatHandler,
        max_entries: int | None = None,
        keep: Literal["first", "last"] = "last",
    ) -> list[LogEntry]:
        if max_entries is not None and max_entries <= 0:
            return []

        if max_entries is None:
            entries: list[LogEntry] | deque[LogEntry] = []
            stop_after = False
        elif keep == "first":
            entries = []
            stop_after = True
        else:
            entries = deque(maxlen=max_entries)
            stop_after = False

        for line in lines:
            if handler.is_record_start(line):
                entry = handler.parse_line(line)
                if entry:
                    if stop_after and len(entries) >= max_entries:
                        break
                    entries.append(entry)
                continue
            if entries:
                self._append_detail(entries[-1], line)

        return list(entries)

    def _detect_handler(self, file_path: Path | str) -> FormatHandler:
        key = str(file_path)
        if key in self._handler_cache:
            return self._handler_cache[key]

        sample: list[str] = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as file:
                for _ in range(200):
                    line = file.readline()
                    if not line:
                        break
                    sample.append(line.rstrip("\n"))
        except OSError:
            sample = []

        handler = detect_handler(sample, path_hint=key)
        self._handler_cache[key] = handler
        return handler

    def _find_time_offset(
        self,
        file_path: Path,
        start_time: datetime,
        handler: FormatHandler,
    ) -> int:
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
                    file.readline()

                timestamp = None
                for _ in range(50):
                    raw = file.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", errors="replace").rstrip("\n")
                    timestamp = handler.peek_timestamp(line)
                    if timestamp is not None:
                        break

                if timestamp is None:
                    high = mid
                    continue

                if timestamp < start_time:
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
        if start_time and start_time.tzinfo is not None:
            start_time = start_time.replace(tzinfo=None)
        if end_time and end_time.tzinfo is not None:
            end_time = end_time.replace(tzinfo=None)
        if start_time and end_time and start_time > end_time:
            return end_time, start_time
        return start_time, end_time

    @staticmethod
    def _append_detail(entry: LogEntry, line: str) -> None:
        entry.raw += "\n" + line
        if entry.details is None:
            entry.details = [line]
        else:
            entry.details.append(line)


def get_logs_root(project_root: str | Path) -> Path:
    return Path(project_root) / "logs"


def detect_log_type(log_file: Path) -> str:
    resources = LogResources()
    try:
        if not log_file.is_file() or log_file.stat().st_size == 0:
            return "empty"
        return resources._detect_handler(log_file).name
    except OSError:
        return "unknown"


def discover_log_files(logs_root: str | Path) -> list[dict[str, Any]]:
    """Legacy metadata discovery used by older demos; prefers .log/.txt."""
    logs_root = Path(logs_root)
    records: list[dict[str, Any]] = []
    if not logs_root.exists():
        return records
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
