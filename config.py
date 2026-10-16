"""Process settings. Environment variables override the defaults."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent

main_llm_config = {
    "model": "us.anthropic.claude-sonnet-5-5",
    "region_name": "us-east-1",
}
tool_llm_config = {
    "model": "us.anthropic.claude-sonnet-5-5",
    "region_name": "us-east-1",
}

BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "5000"))
BACKEND_URL = os.getenv("BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")



# Soft cap on tool rounds in query mode.
DEFAULT_MAX_TOOL_ROUNDS = int(os.getenv("DEFAULT_MAX_TOOL_ROUNDS", "5"))

MODE_SCHEDULED = "scheduled"
MODE_QUERY = "query"
ANALYSIS_MODES = (MODE_SCHEDULED, MODE_QUERY)

# A query either starts on a log file, or continues from a scheduled report.
QUERY_SOURCE_NEW = "new"
QUERY_SOURCE_SCHEDULED = "scheduled"
QUERY_SOURCES = (QUERY_SOURCE_NEW, QUERY_SOURCE_SCHEDULED)

# scheduled_20261015T171400_ab12cd34
THREAD_ID_TIME_FORMAT = "%Y%m%dT%H%M%S"
THREAD_TIME_DISPLAY_FORMAT = "%Y-%m-%d %H:%M:%S"


def tool_limit(name: str, default: int) -> int:
    """Read a positive int setting. A missing or invalid value uses `default`."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def log_roots() -> list[Path]:
    """Folders the tools are allowed to read. Defaults to the repo `logs` folder.

    Override with LOG_ROOTS, a semicolon-separated list of absolute paths.
    """
    raw = os.getenv("LOG_ROOTS", "").strip()
    if not raw:
        return [REPO_ROOT / "logs"]
    roots = [Path(part.strip()) for part in raw.split(";") if part.strip()]
    return roots or [REPO_ROOT / "logs"]


def new_thread_id(mode: str) -> str:
    """Thread id with the mode and the local start time, so a run can be picked later."""
    if mode not in ANALYSIS_MODES:
        raise ValueError(f"Invalid analysis mode: {mode}")
    stamp = datetime.now().strftime(THREAD_ID_TIME_FORMAT)
    return f"{mode}_{stamp}_{uuid4().hex[:8]}"


def thread_timestamp(thread_id: str) -> str:
    """Display time stored in a thread id. Empty when the id has no timestamp."""
    parts = thread_id.split("_")
    if len(parts) < 2:
        return ""
    try:
        parsed = datetime.strptime(parts[1], THREAD_ID_TIME_FORMAT)
    except ValueError:
        return ""
    return parsed.strftime(THREAD_TIME_DISPLAY_FORMAT)
