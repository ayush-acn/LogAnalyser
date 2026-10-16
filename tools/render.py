"""Turn parsed entries into short text the model can read."""

from __future__ import annotations

from collections import Counter
from datetime import datetime

from tools.parsers.base import LogEntry
from tools.reader import ScanResult
from tools.settings import max_detail_lines, max_tool_output_chars
from tools.triage import ProblemGroup


def _stamp(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _trim_details(details: list[str]) -> list[str]:
    """Keep the first lines plus every 'Caused by' line, then say how many were cut."""
    keep = max_detail_lines()
    head = details[:keep]
    caused = [
        line
        for line in details
        if line.strip().lower().startswith("caused by") and line not in head
    ]
    omitted = len(details) - len(head) - len(caused)
    trimmed = head + caused
    if omitted > 0:
        trimmed.append(f"... (+{omitted} lines)")
    return trimmed


def format_entry(entry: LogEntry) -> str:
    """One compact line, plus a trimmed stack trace when the entry has one."""
    parts: list[str] = [f"L{entry.line_number if entry.line_number is not None else '?'}"]
    if entry.timestamp is not None:
        parts.append(_stamp(entry.timestamp))
    if entry.level:
        parts.append(entry.level)
    if entry.source:
        parts.append(f"[{entry.source}]")
    message = " ".join((entry.message or "").split())
    parts.append(message)
    lines = [" ".join(parts)]
    if entry.details:
        lines.extend(_trim_details(entry.details))
    return "\n".join(lines)


def _sections(entries: list[LogEntry]) -> list[str]:
    """Group lines under the file they came from, in the order given."""
    blocks: list[str] = []
    current_path: str | None = None
    bucket: list[str] = []

    def flush() -> None:
        if current_path is None:
            return
        blocks.append(f"== {current_path} ==")
        blocks.extend(bucket)

    for entry in entries:
        path = entry.file_path or "(unknown file)"
        if path != current_path:
            flush()
            current_path = path
            bucket = []
        bucket.append(format_entry(entry))
    flush()
    return blocks


def cap_text(text: str) -> str:
    """Cut long tool output and say that it was cut."""
    limit = max_tool_output_chars()
    if len(text) <= limit:
        return text
    note = "\n... (output truncated to the character budget)"
    keep = max(0, limit - len(note))
    return text[:keep].rstrip() + note


def render_overview(scan: ScanResult, groups: list[ProblemGroup], group_total: int) -> str:
    timestamps = [entry.timestamp for entry in scan.entries if entry.timestamp is not None]
    if timestamps:
        span = f"{_stamp(min(timestamps))} to {_stamp(max(timestamps))}"
    else:
        span = "no timestamps"
    counts = Counter((entry.level or "NONE").upper() for entry in scan.entries)
    count_text = ", ".join(f"{level} {counts[level]}" for level in sorted(counts)) or "none"
    files = ", ".join(scan.files) if scan.files else "none"
    lines = [
        (
            f"Coverage: {len(scan.files)} file(s), {span}, "
            f"{scan.entries_scanned} entries, {scan.lines_scanned} lines. "
            f"Truncated: {'yes' if scan.truncated else 'no'}."
        ),
        f"Window: {scan.window}",
        f"Files: {files}",
        f"Counts: {count_text}",
        "",
    ]
    if not groups:
        lines.append("Problem groups: none. No warnings or errors in this window.")
        return cap_text("\n".join(lines))

    shown = len(groups)
    lines.append(f"Problem groups: showing {shown} of {group_total}.")
    for index, group in enumerate(groups, start=1):
        sample = group.sample
        location = sample.file_path or "(unknown file)"
        if sample.line_number is not None:
            location = f"{location}:{sample.line_number}"
        level = group.level or "NONE"
        lines.append(
            f"{index}. {group.fingerprint} {level} x{group.count} "
            f"first {_stamp(group.first_seen)} last {_stamp(group.last_seen)} "
            f"sample {location}"
        )
        lines.append(f"   {' '.join((sample.message or '').split())}")
    lines.append(
        "Cite a group with the sample path and the line number after 'sample'. "
        "Call get_context on that line when the message alone is not enough."
    )
    return cap_text("\n".join(lines))


def render_search(entries: list[LogEntry], matched: int, scan: ScanResult) -> str:
    header = (
        f"Showing {len(entries)} of {matched} matches. "
        f"Truncated: {'yes' if scan.truncated else 'no'}. "
        f"Window: {scan.window}"
    )
    if not entries:
        return cap_text(header + "\nNo matches in this window.")
    body = "\n".join(_sections(entries))
    return cap_text(header + "\n" + body)


def render_context(path: str, rows: list[tuple[int, str]]) -> str:
    lines = [f"== {path} =="]
    lines.extend(f"L{number} {text}" for number, text in rows)
    return cap_text("\n".join(lines))
