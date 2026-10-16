from __future__ import annotations

from typing import Generator

from agent import SCHEDULED_THREAD_CLOSED, scheduled_thread_is_new, stream_turn
from backend.helpers import ensure_thread_id, sse_line
from config import MODE_SCHEDULED, QUERY_SOURCE_NEW


def iter_sse_events(
    *,
    mode: str,
    log_file_path: str,
    user_query: str | None,
    thread_id: str | None,
    query_source: str = QUERY_SOURCE_NEW,
    scheduled_thread_id: str | None = None,
    response_type: str = "TEXT",
) -> Generator[str, None, None]:
    """
    Yield Server-Sent Event lines for one analysis turn.

    Events:
      data: {"type":"meta","thread_id":"..."}
      data: {"type":"token","text":"..."}
      data: {"type":"done","issues":...|null}
    """
    tid = ensure_thread_id(mode, thread_id)
    if mode == MODE_SCHEDULED:
        user_query = None
        query_source = QUERY_SOURCE_NEW
        scheduled_thread_id = None
        if not scheduled_thread_is_new(tid):
            yield sse_line({"type": "error", "message": SCHEDULED_THREAD_CLOSED})
            yield sse_line({"type": "done", "issues": None})
            return

    yield sse_line({"type": "meta", "thread_id": tid})

    try:
        for event in stream_turn(
            thread_id=tid,
            log_file_path=log_file_path,
            user_query=user_query,
            mode=mode,
            query_source=query_source,
            scheduled_thread_id=scheduled_thread_id,
            response_type=response_type,
        ):
            yield sse_line(event)
    except Exception as exc:
        yield sse_line({"type": "error", "message": str(exc)})
        yield sse_line({"type": "done", "issues": None})
