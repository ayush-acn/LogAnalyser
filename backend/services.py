from __future__ import annotations

import json
from typing import Generator

from LogAgent_chat import graph, new_chat, stream_turn
from frontend_utils import generate_thread_id
from langchain_core.messages import SystemMessage


def _ensure_thread_id(mode: str, thread_id: str | None) -> str:
    if thread_id:
        return thread_id
    return generate_thread_id(mode)


def _is_new_thread(thread_id: str) -> bool:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = graph.get_state(config)
        values = snapshot.values if snapshot else {}
        messages = values.get("messages") if isinstance(values, dict) else None
        return not messages
    except Exception:
        return True


def iter_sse_events(
    *,
    mode: str,
    log_file_path: str,
    user_query: str | None,
    thread_id: str | None,
) -> Generator[str, None, None]:
    """
    Yield Server-Sent Event lines for an analysis turn.
    Events:
      data: {"type":"meta","thread_id":"..."}
      data: {"type":"token","text":"..."}
      data: {"type":"done","issues":...|null}
    """
    tid = _ensure_thread_id(mode, thread_id)
    # Display/history list mutated like the old FE contract; only new msgs go to graph.
    messages: list = []
    if _is_new_thread(tid):
        # Pre-seed so stream_turn adds system+human as new messages.
        pass
    else:
        # Non-empty marker so stream_turn skips re-sending the system prompt.
        messages.append(SystemMessage(content=new_chat(log_file_path, user_query)))

    yield _sse({"type": "meta", "thread_id": tid})

    for event in stream_turn(messages, tid, log_file_path, user_query):
        yield _sse(event)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"
