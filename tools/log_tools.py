"""The three log tools given to the agent.

log_overview   summarise problems in the newest part of a file
search_logs    find lines by text or level
get_context    show the lines around a citation

Rotation groups, parsing, and size limits stay inside the tools.
"""

from __future__ import annotations

from langchain_core.tools import tool

from tools.access import resolve_allowed_file
from tools.helpers import open_log_group, parse_levels, parse_time
from tools.reader import read_context_lines, scan_logs
from tools.render import render_context, render_overview, render_search
from tools.settings import (
    default_search_limit,
    max_context_lines,
    max_search_limit,
    overview_group_limit,
)
from tools.triage import group_problems


@tool("log_overview")
def log_overview(
    file_path: str,
    start_time: str | None = None,
    end_time: str | None = None,
) -> str:
    """Summarise problems in a log file and its rotated copies.

    Call this first. Without a time range it reads the newest part of the file
    only, so large or old files stay out of context.

    Args:
        file_path: Absolute path to the log file.
        start_time: Optional inclusive start, format YYYY-MM-DD HH:MM:SS.
        end_time: Optional inclusive end, format YYYY-MM-DD HH:MM:SS.
    """
    try:
        start = parse_time(start_time)
        end = parse_time(end_time)
    except ValueError as exc:
        return str(exc)

    paths, error = open_log_group(file_path)
    if error:
        return error
    scan = scan_logs(paths, start_time=start, end_time=end)
    if not scan.entries:
        return (
            f"Coverage: {len(scan.files)} file(s), no entries in this window. "
            f"Truncated: {'yes' if scan.truncated else 'no'}. Window: {scan.window}"
        )
    groups = group_problems(scan.entries, limit=10**6)
    shown = groups[: overview_group_limit()]
    return render_overview(scan, shown, len(groups))


@tool("search_logs")
def search_logs(
    file_path: str,
    text: str | None = None,
    levels: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 30,
) -> str:
    """Find log entries by text and/or level inside the same scan window as log_overview.

    Args:
        file_path: Absolute path to the log file.
        text: Case-insensitive substring. Optional when levels is set.
        levels: Comma-separated levels, for example "ERROR,WARN".
        start_time: Optional inclusive start, format YYYY-MM-DD HH:MM:SS.
        end_time: Optional inclusive end, format YYYY-MM-DD HH:MM:SS.
        limit: How many of the newest matches to return.
    """
    query = (text or "").strip()
    wanted = parse_levels(levels)
    if not query and not wanted:
        return "Provide text or levels to search. An empty search is not run."
    try:
        start = parse_time(start_time)
        end = parse_time(end_time)
        cap = int(limit) if limit else default_search_limit()
    except ValueError as exc:
        return str(exc)
    cap = max(1, min(cap, max_search_limit()))

    paths, error = open_log_group(file_path)
    if error:
        return error
    scan = scan_logs(paths, start_time=start, end_time=end)
    needle = query.lower()
    matched = []
    for entry in scan.entries:
        if wanted and (entry.level or "").upper() not in wanted:
            continue
        if needle:
            haystack = entry.message or ""
            if entry.details:
                haystack = haystack + "\n" + "\n".join(entry.details)
            if needle not in haystack.lower():
                continue
        matched.append(entry)
    newest = matched[-cap:]
    return render_search(newest, len(matched), scan)


@tool("get_context")
def get_context(
    file_path: str,
    line_number: int,
    before: int = 10,
    after: int = 10,
) -> str:
    """Show the raw lines around a cited line. Use this after log_overview or search_logs.

    Args:
        file_path: Absolute path of the file named in the citation.
        line_number: 1-based line number from the tool output.
        before: Lines to include before the citation.
        after: Lines to include after the citation.
    """
    try:
        path = resolve_allowed_file(file_path)
        number = int(line_number)
        side_cap = max_context_lines()
        before_n = max(0, min(int(before), side_cap))
        after_n = max(0, min(int(after), side_cap))
    except (OSError, ValueError) as exc:
        return str(exc)
    if number < 1:
        return "line_number must be 1 or greater."
    rows, found = read_context_lines(path, number, before_n, after_n)
    if not found:
        return f"Line {number} is past the end of {path.resolve()}."
    return render_context(str(path.resolve()), rows)


LOG_TOOLS = [log_overview, search_logs, get_context]
