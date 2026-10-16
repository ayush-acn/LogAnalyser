"""Read log files without loading a whole rotation group into memory.

A scan without a time range reads from the newest end, up to a byte budget.
A time range seeks near the start time, then reads forward, and stops at the
byte budget instead of dropping lines silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tools.parsers.base import FormatHandler, LogEntry
from tools.parsers.registry import detect_handler
from tools.settings import scan_max_bytes


@dataclass
class ScanResult:
    """Entries collected from one scan, plus what the scan did not cover."""

    entries: list[LogEntry] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    entries_scanned: int = 0
    lines_scanned: int = 0
    truncated: bool = False
    window: str = ""


def detect_log_type(log_file: Path) -> str:
    """Name of the format chosen for this file."""
    try:
        if not log_file.is_file() or log_file.stat().st_size == 0:
            return "empty"
        return _detect_handler(log_file).name
    except OSError:
        return "unknown"


def scan_logs(
    paths: list[Path],
    *,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    max_bytes: int | None = None,
) -> ScanResult:
    """Read `paths` (oldest first) as one continuous log."""
    budget = max_bytes if max_bytes is not None else scan_max_bytes()
    start_time, end_time = _normalize_time_range(start_time, end_time)
    existing = [path for path in paths if path.is_file() and path.stat().st_size > 0]
    if not existing:
        return ScanResult(window=_window_label(start_time, end_time, budget))

    if start_time or end_time:
        result = _scan_time_range(existing, start_time, end_time, budget)
    else:
        result = _scan_tail(existing, budget)
    result.window = _window_label(start_time, end_time, budget)
    result.entries_scanned = len(result.entries)
    return result


def read_context_lines(
    path: Path,
    line_number: int,
    before: int,
    after: int,
) -> tuple[list[tuple[int, str]], bool]:
    """Return `(line number, text)` around `line_number`. The bool is whether that line exists."""
    start = max(1, line_number - before)
    end = line_number + after
    rows: list[tuple[int, str]] = []
    found = False
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, start=1):
            if number < start:
                continue
            if number > end:
                break
            if number == line_number:
                found = True
            rows.append((number, line.rstrip("\r\n")))
    return rows, found


def _window_label(
    start_time: datetime | None,
    end_time: datetime | None,
    budget: int,
) -> str:
    if start_time or end_time:
        start = start_time.strftime("%Y-%m-%d %H:%M:%S") if start_time else "beginning"
        end = end_time.strftime("%Y-%m-%d %H:%M:%S") if end_time else "end"
        return f"time range {start} to {end}, byte budget {budget}"
    return f"newest {budget} bytes of the rotation group"


def _scan_tail(paths: list[Path], budget: int) -> ScanResult:
    """Walk newest file to oldest, and stop once the byte budget is spent."""
    remaining = budget
    chunks: list[tuple[Path, list[str], int]] = []
    truncated = False
    for path in reversed(paths):
        if remaining <= 0:
            truncated = True
            break
        size = path.stat().st_size
        lines, start_line, file_truncated = _read_tail(path, remaining)
        chunks.append((path, lines, start_line))
        remaining -= min(size, remaining)
        if file_truncated:
            truncated = True
            break
    chunks.reverse()
    return _parse_chunks(chunks, truncated, start_time=None, end_time=None)


def _scan_time_range(
    paths: list[Path],
    start_time: datetime | None,
    end_time: datetime | None,
    budget: int,
) -> ScanResult:
    remaining = budget
    chunks: list[tuple[Path, list[str], int]] = []
    truncated = False
    for path in paths:
        if remaining <= 0:
            truncated = True
            break
        handler = _detect_handler(path)
        if _outside_time_range(path, handler, start_time, end_time):
            continue
        offset = _find_time_offset(path, start_time, handler) if start_time else 0
        lines, start_line, file_truncated = _read_forward(path, offset, remaining)
        if not lines:
            continue
        chunks.append((path, lines, start_line))
        remaining -= min(path.stat().st_size - offset, remaining)
        if file_truncated:
            truncated = True
            # A later file might still be inside the range, but the budget is spent.
            break
    result = _parse_chunks(chunks, truncated, start_time=start_time, end_time=end_time)
    return result


def _parse_chunks(
    chunks: list[tuple[Path, list[str], int]],
    truncated: bool,
    *,
    start_time: datetime | None,
    end_time: datetime | None,
) -> ScanResult:
    entries: list[LogEntry] = []
    files: list[str] = []
    lines_scanned = 0
    reached_end = False
    for path, lines, start_line in chunks:
        handler = _detect_handler(path)
        parsed, stopped = _parse_lines(
            lines,
            handler,
            file_path=path,
            start_line=start_line,
            start_time=start_time,
            end_time=end_time,
        )
        entries.extend(parsed)
        files.append(str(path.resolve()))
        lines_scanned += len(lines)
        if stopped:
            reached_end = True
            break
    if reached_end:
        truncated = False
    return ScanResult(
        entries=entries,
        files=files,
        lines_scanned=lines_scanned,
        truncated=truncated,
    )


def _parse_lines(
    lines: list[str],
    handler: FormatHandler,
    *,
    file_path: Path,
    start_line: int,
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[list[LogEntry], bool]:
    """Return entries and whether a record past `end_time` ended the scan."""
    entries: list[LogEntry] = []
    keep = False
    bounded = start_time is not None or end_time is not None
    line_number = start_line
    for line in lines:
        current = line_number
        line_number += 1
        if handler.is_record_start(line):
            timestamp = handler.peek_timestamp(line)
            if end_time is not None and timestamp is not None and timestamp > end_time:
                return entries, True
            if bounded and (timestamp is None or (start_time is not None and timestamp < start_time)):
                keep = False
                continue
            entry = handler.parse_line(line)
            if entry is None:
                keep = False
                continue
            entry.file_path = str(file_path.resolve())
            entry.line_number = current
            entries.append(entry)
            keep = True
            continue
        if keep and entries:
            _append_detail(entries[-1], line)
    return entries, False


def _read_tail(path: Path, max_bytes: int) -> tuple[list[str], int, bool]:
    """Lines from the end of the file. The bool is true when older bytes were left out."""
    size = path.stat().st_size
    if size <= max_bytes:
        text = path.read_bytes().decode("utf-8", errors="replace")
        return text.splitlines(), 1, False

    offset = size - max_bytes
    with open(path, "rb") as handle:
        handle.seek(offset)
        raw = handle.read(max_bytes)
    offset, raw = _drop_partial_first_line(path, offset, raw)
    start_line = _line_number_at_offset(path, offset)
    return raw.decode("utf-8", errors="replace").splitlines(), start_line, True


def _read_forward(path: Path, offset: int, max_bytes: int) -> tuple[list[str], int, bool]:
    """Lines from `offset`, at most `max_bytes`. The bool is true when more bytes remain."""
    size = path.stat().st_size
    if offset < 0:
        offset = 0
    if offset >= size:
        return [], _line_number_at_offset(path, offset), False
    available = size - offset
    to_read = min(available, max_bytes)
    truncated = available > max_bytes
    with open(path, "rb") as handle:
        handle.seek(offset)
        raw = handle.read(to_read)
    if truncated:
        newline = raw.rfind(b"\n")
        if newline >= 0:
            raw = raw[:newline]
    offset, raw = _drop_partial_first_line(path, offset, raw)
    start_line = _line_number_at_offset(path, offset)
    return raw.decode("utf-8", errors="replace").splitlines(), start_line, truncated


def _drop_partial_first_line(path: Path, offset: int, raw: bytes) -> tuple[int, bytes]:
    """If `offset` lands in the middle of a line, start at the next line."""
    if offset <= 0 or not raw or not _starts_mid_line(path, offset):
        return offset, raw
    newline = raw.find(b"\n")
    if newline < 0:
        return offset + len(raw), b""
    return offset + newline + 1, raw[newline + 1 :]


def _starts_mid_line(path: Path, offset: int) -> bool:
    if offset <= 0:
        return False
    with open(path, "rb") as handle:
        handle.seek(offset - 1)
        return handle.read(1) != b"\n"


def _outside_time_range(
    path: Path,
    handler: FormatHandler,
    start_time: datetime | None,
    end_time: datetime | None,
) -> bool:
    """Skip a whole file when its timestamps sit entirely outside the range."""
    if start_time is None and end_time is None:
        return False
    first = _edge_timestamp(path, handler, newest=False)
    last = _edge_timestamp(path, handler, newest=True)
    if start_time is not None and last is not None and last < start_time:
        return True
    if end_time is not None and first is not None and first > end_time:
        return True
    return False


def _edge_timestamp(path: Path, handler: FormatHandler, *, newest: bool) -> datetime | None:
    """First or last timestamp in a small slice of the file. None when the slice has none."""
    window = 64 * 1024
    size = path.stat().st_size
    with open(path, "rb") as handle:
        if newest and size > window:
            handle.seek(size - window)
            handle.readline()
        raw = handle.read(window)
    found = None
    for line in raw.decode("utf-8", errors="replace").splitlines():
        timestamp = handler.peek_timestamp(line)
        if timestamp is None:
            continue
        if not newest:
            return timestamp
        found = timestamp
    return found


def _find_time_offset(path: Path, start_time: datetime, handler: FormatHandler) -> int:
    """Byte position near `start_time`. Small files are read from the beginning."""
    size = path.stat().st_size
    if size < 64 * 1024:
        return 0

    low, high = 0, size
    best = 0
    with open(path, "rb") as handle:
        for _ in range(64):
            if high - low < 256:
                break
            mid = (low + high) // 2
            handle.seek(mid)
            if mid > 0:
                handle.readline()

            timestamp = None
            for _ in range(50):
                raw = handle.readline()
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
                low = handle.tell()
                best = low
            else:
                high = mid
    return max(0, best)


def _line_number_at_offset(path: Path, offset: int) -> int:
    if offset <= 0:
        return 1
    count = 0
    remaining = offset
    with open(path, "rb") as handle:
        while remaining > 0:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            count += chunk.count(b"\n")
            remaining -= len(chunk)
    return count + 1


def _detect_handler(path: Path) -> FormatHandler:
    sample: list[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for _ in range(200):
                line = handle.readline()
                if not line:
                    break
                sample.append(line.rstrip("\n"))
    except OSError:
        sample = []
    return detect_handler(sample, path_hint=str(path))


def _normalize_time_range(
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    if start_time is not None and start_time.tzinfo is not None:
        start_time = start_time.replace(tzinfo=None)
    if end_time is not None and end_time.tzinfo is not None:
        end_time = end_time.replace(tzinfo=None)
    if start_time is not None and end_time is not None and start_time > end_time:
        return end_time, start_time
    return start_time, end_time


def _append_detail(entry: LogEntry, line: str) -> None:
    entry.raw += "\n" + line
    if entry.details is None:
        entry.details = [line]
    else:
        entry.details.append(line)
