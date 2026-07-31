from __future__ import annotations

from datetime import datetime

from Tools.handlers.base import LogEntry


class UtilityBannerHandler:
    """
    Untimestamped utility console captures. Treat blank-line-separated
    paragraphs as records; detect only when no other handler matches.
    Registered before raw; registry order decides detect priority.
    """

    name = "utility_banner"

    def detect(self, sample_lines: list[str]) -> bool:
        non_empty = [line for line in sample_lines if line.strip()]
        if not non_empty:
            return False
        # Heuristic: banner stars / utility name lines, no timestamped headers.
        bannerish = sum(
            1
            for line in non_empty
            if line.strip().startswith("*") or "utility" in line.lower() or "preferences_manager" in line.lower()
        )
        return bannerish >= 1 and len(non_empty) >= 2

    def is_record_start(self, line: str) -> bool:
        # New record on non-empty line after blank, or lines of stars.
        stripped = line.strip()
        if not stripped:
            return False
        return stripped.startswith("*") or stripped.startswith("preferences_manager")

    def peek_timestamp(self, line: str) -> datetime | None:
        return None

    def parse_line(self, line: str) -> LogEntry | None:
        if not line.strip():
            return None
        if not self.is_record_start(line):
            return None
        return LogEntry(
            log_type=self.name,
            timestamp=None,
            level=None,
            message=line.strip(),
            raw=line,
        )
