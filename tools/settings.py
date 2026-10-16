"""Limits for reading and rendering logs. Values come from the environment via config."""

from __future__ import annotations

from config import tool_limit


def scan_max_bytes() -> int:
    """How much of a rotation group a scan reads from the newest end."""
    return tool_limit("LOG_SCAN_MAX_BYTES", 20 * 1024 * 1024)


def max_tool_output_chars() -> int:
    return tool_limit("MAX_TOOL_OUTPUT_CHARS", 12_000)


def max_detail_lines() -> int:
    return tool_limit("MAX_DETAIL_LINES", 15)


def overview_group_limit() -> int:
    return tool_limit("OVERVIEW_GROUP_LIMIT", 15)


def default_search_limit() -> int:
    return tool_limit("DEFAULT_SEARCH_LIMIT", 30)


def max_search_limit() -> int:
    return tool_limit("MAX_SEARCH_LIMIT", 100)


def max_context_lines() -> int:
    return tool_limit("MAX_CONTEXT_LINES", 50)


def default_max_discover() -> int:
    return tool_limit("DEFAULT_MAX_DISCOVER", 500)
