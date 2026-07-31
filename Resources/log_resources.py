"""Thin re-export — prefer Tools.log_resources."""

from Tools.log_resources import (  # noqa: F401
    LogEntry,
    LogResources,
    detect_log_type,
    discover_log_files,
    filter_records,
    get_logs_root,
    list_folders,
    list_log_types,
)
