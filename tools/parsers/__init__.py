"""Log format parsers. `detect_parser` picks a format; `LogEntry` is one record."""

from tools.parsers.base import FormatHandler, LogEntry
from tools.parsers.registry import detect_handler as detect_parser

__all__ = [
    "FormatHandler",
    "LogEntry",
    "detect_parser",
]
