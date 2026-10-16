"""One-line traces for model and tool steps.

Written to agent.log in the repo root, and passed on to the process log.
The agent runs in the Flask process, so these lines show up there and in the file.
"""

from __future__ import annotations

import logging

from config import REPO_ROOT

LOG_PATH = REPO_ROOT / "agent.log"

logger = logging.getLogger("loganalyser")
logger.setLevel(logging.INFO)
logger.propagate = True

if not any(getattr(handler, "agent_log", False) for handler in logger.handlers):
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    file_handler.agent_log = True  # type: ignore[attr-defined]
    logger.addHandler(file_handler)


def trace(step: str, **details: object) -> None:
    parts = [step]
    for key, value in details.items():
        text = " ".join(str(value).split())
        if len(text) > 240:
            text = text[:240] + "..."
        parts.append(f"{key}={text}")
    logger.info(" | ".join(parts))
    for handler in logger.handlers:
        handler.flush()
