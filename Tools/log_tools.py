from __future__ import annotations

from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from Tools import DEFAULT_LATEST_LOGS, DEFAULT_MAX_DISCOVER, MAX_LOGS_PER_CALL
from Tools.log_discovery import discover_logs, resolve_log_group
from Tools.log_resources import LogResources


def _as_path(file_path: str | Path) -> Path:
    return file_path if isinstance(file_path, Path) else Path(file_path)


def _clamp_n(n: int | None) -> int:
    count = n if n is not None else DEFAULT_LATEST_LOGS
    return max(1, min(int(count), MAX_LOGS_PER_CALL))


def _resolve_paths(file_path: str, include_rotations: bool) -> list[Path]:
    path = _as_path(file_path)
    if include_rotations:
        group = resolve_log_group(path)
        return group if group else [path]
    return [path]


def _fetch(
    file_path: str,
    *,
    n: int,
    skip: int = 0,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    include_rotations: bool = True,
) -> list[dict]:
    paths = _resolve_paths(file_path, include_rotations)
    resources = LogResources()
    if len(paths) == 1:
        return resources.fetch_logs(
            paths[0],
            start_time=start_time,
            end_time=end_time,
            skip=skip,
            n=n,
        )
    return resources.fetch_logs_from_paths(
        paths,
        start_time=start_time,
        end_time=end_time,
        skip=skip,
        n=n,
    )


@tool("list_logs")
def list_logs(root_dir: str, max_files: int = DEFAULT_MAX_DISCOVER) -> list[dict]:
    """
    Recursively list log files under a root directory (newest first).
    Use when you only have a folder path and need to find which logs exist.
    """
    limit = max(1, min(int(max_files or DEFAULT_MAX_DISCOVER), DEFAULT_MAX_DISCOVER * 2))
    files = discover_logs(root_dir, max_files=limit)
    return [{"path": str(path.resolve()), "name": path.name, "size": path.stat().st_size} for path in files]


@tool("resolve_log_group")
def resolve_log_group_tool(file_path: str) -> list[str]:
    """
    Resolve a log file to its full rotation/split group, oldest to newest.
    Use before fetching when a log may be split across dated or numbered files.
    """
    return [str(path.resolve()) for path in resolve_log_group(file_path)]


@tool("latest_logs")
def fetch_latest_logs(
    file_path: str,
    n: int = DEFAULT_LATEST_LOGS,
    skip: int = 0,
    include_rotations: bool = True,
) -> list[dict]:
    """
    Fetch the most recent log entries from a log file (and its rotations by default).
    Use when:
    - No specific time range is mentioned.
    - You want a general health check of recent activity.
    - You need to page through older logs (use skip).
    Args:
        file_path: Full path to the log file.
        n: Number of log entries to return (default 10, configurable max).
        skip: Entries to skip from the bottom before returning n (pagination).
        include_rotations: If true, merge sibling rotated/split files first.
    """
    return _fetch(
        file_path,
        n=_clamp_n(n),
        skip=max(0, skip or 0),
        include_rotations=include_rotations,
    )


@tool("page_logs")
def fetch_paginated_logs(
    file_path: str,
    n: int = DEFAULT_LATEST_LOGS,
    skip: int = 0,
    include_rotations: bool = True,
) -> list[dict]:
    """
    Fetch paginated log entries from a log file (and rotations by default).
    Use skip to page further back from the end of the log.
    """
    return _fetch(
        file_path,
        n=_clamp_n(n),
        skip=max(0, skip or 0),
        include_rotations=include_rotations,
    )


@tool("timed_logs")
def fetch_timed_logs(
    file_path: str,
    start_time: datetime,
    end_time: datetime,
    n: int = DEFAULT_LATEST_LOGS,
    include_rotations: bool = True,
) -> list[dict]:
    """
    Fetch log entries within a specific time range (merging rotations by default).
    Args:
        file_path: Path to the log file.
        start_time: Start of the inclusive time range.
        end_time: End of the inclusive time range.
        n: Max entries to return from that range (default/max configurable).
        include_rotations: If true, merge sibling rotated/split files first.
    """
    logs = _fetch(
        file_path,
        n=_clamp_n(n) * 50,  # gather a wider window then clamp
        start_time=start_time,
        end_time=end_time,
        include_rotations=include_rotations,
    )
    return logs[-_clamp_n(n) :]


log_fetch_tools = [
    list_logs,
    resolve_log_group_tool,
    fetch_latest_logs,
    fetch_paginated_logs,
    fetch_timed_logs,
]
