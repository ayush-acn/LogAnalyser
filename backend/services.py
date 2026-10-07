from __future__ import annotations

import json
from typing import Generator

from LogAgent_chat import stream_turn
from frontend_utils import generate_thread_id


def _ensure_thread_id(mode: str, thread_id: str | None) -> str:
    if thread_id:
        return thread_id
    return generate_thread_id(mode)


def iter_sse_events(
    *,
    mode: str,
    log_file_path: str,
    user_query: str | None,
    thread_id: str | None,
) -> Generator[str, None, None]:
    """
    Yield Server-Sent Event lines for one analysis turn.

    Events:
      data: {"type":"meta","thread_id":"..."}
      data: {"type":"token","text":"..."}
      data: {"type":"done","issues":...|null}
    """
    tid = _ensure_thread_id(mode, thread_id)
    yield _sse({"type": "meta", "thread_id": tid})

    try:
        for event in stream_turn(
            thread_id=tid,
            log_file_path=log_file_path,
            user_query=user_query,
            mode=mode,
        ):
            yield _sse(event)
    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})
        yield _sse({"type": "done", "issues": None})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"
