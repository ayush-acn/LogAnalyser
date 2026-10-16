from pathlib import Path

from config import MODE_QUERY, MODE_SCHEDULED, new_thread_id, thread_timestamp
from tools.access import resolve_allowed_dir
from tools.discovery import discover_logs


def generate_thread_id(mode: str) -> str:
    """Thread id for a query chat or a scheduled report. Includes the start time."""
    return new_thread_id(mode)


def discover_log_files(logs_root: Path) -> list[Path]:
    """Log files under `logs_root`, newest first. The folder must be inside an allowed root."""
    return discover_logs(resolve_allowed_dir(logs_root))


def thread_label(mode: str, text: str | None, thread_id: str) -> str:
    """Sidebar label. The time comes from the thread id."""
    when = thread_timestamp(thread_id)
    titles = {
        MODE_SCHEDULED: "Scheduled analysis",
        MODE_QUERY: "Query",
    }
    base = text.strip() if text else titles.get(mode, mode)
    base = base[:40] + ("..." if len(base) > 40 else "")
    return f"{base}  {when}".strip()
