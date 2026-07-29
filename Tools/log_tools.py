import sys
from pathlib import Path
from datetime import datetime


from langchain_core.tools import tool
from Tools.log_resources import LogResources
from Tools import DEFAULT_LATEST_LOGS

MAX_LOGS_PER_CALL = 20


def _as_path(file_path: str | Path) -> Path:
    return file_path if isinstance(file_path, Path) else Path(file_path)


def _clamp_n(n: int | None) -> int:
    count = n if n is not None else DEFAULT_LATEST_LOGS
    return max(1, min(int(count), MAX_LOGS_PER_CALL))


@tool("latest_logs")
def fetch_latest_logs(file_path: str, n: int = DEFAULT_LATEST_LOGS, skip: int = 0) -> list[dict]:
    """
    Fetch the most recent log entries from a log file.
    Use this tool when:
    - No specific time range is mentioned.
    - You want a general health check of recent activity.
    - You need to page through older logs (use skip to skip entries).
    Args:
        file_path: Full path to the log file.
        n: Number of log entries to return (max 20). Defaults to 10.
        skip: Number of entries to skip from the bottom before
              returning `n` entries. Use for pagination.
              Example: skip=10, n=10 gives entries 11-20 from the bottom.
    """
    return LogResources().fetch_logs(_as_path(file_path), n=_clamp_n(n), skip=max(0, skip or 0))


@tool("page_logs")
def fetch_paginated_logs(file_path: str, n: int = DEFAULT_LATEST_LOGS, skip: int = 0) -> list[dict]:
    """
    Fetch paginated log entries from a log file.
    Use this tool when:
    - You want to page through older logs (use skip to skip entries).
    Args:
        file_path: Path to the log file.
        n: Number of log entries to return (max 20). Defaults to 10.
        skip: Number of entries to skip from the bottom before returning `n` entries.
    """
    return LogResources().fetch_logs(_as_path(file_path), n=_clamp_n(n), skip=max(0, skip or 0))


@tool("timed_logs")
def fetch_timed_logs(
    file_path: str,
    start_time: datetime,
    end_time: datetime,
    n: int = MAX_LOGS_PER_CALL,
) -> list[dict]:
    """
    Fetch log entries from a log file within a specific time range.
    Use this tool when:
    - You want to fetch logs within a specific time range.
    Args:
        file_path: Path to the log file.
        start_time: Start time of the time range.
        end_time: End time of the time range.
        n: Max number of log entries to return from that range (max 20).
    """
    logs = LogResources().fetch_logs(
        _as_path(file_path),
        start_time=start_time,
        end_time=end_time,
    )
    # Time-range fetch can be large; keep a hard cap for the agent loop.
    return logs[-_clamp_n(n) :]


log_fetch_tools = [fetch_latest_logs, fetch_paginated_logs, fetch_timed_logs]


if __name__ == "__main__":
    logs_dir = '..' / "logs" / "LOGS_POOL_DUMP" / "PoolServer1"
    sample_path = str(logs_dir / "ServerManager.log")

    print(f"Tool name: {fetch_latest_logs.name}")
    print(f"Sample path: {sample_path}")

    logs = fetch_latest_logs.invoke({
        "file_path": sample_path,
        "n": 10,
        "skip": 0,
    })

    print(f"Fetched {len(logs)} log entries")
