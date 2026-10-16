from __future__ import annotations

from typing import Generator

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.formatting import message_text
from agent.graph import build_graph
from agent.helpers import (
    CONTINUE_AFTER_NARRATED_TOOL,
    DEFAULT_SCHEDULED_QUERY,
    SCHEDULED_THREAD_CLOSED,
    display_text,
    has_tool_calls,
    narrated_tool_call,
    query_with_scheduled_report,
    system_prompt_for,
    thread_is_empty,
)
from agent.schemas import IssuesReported
from agent.tracing import trace
from config import ANALYSIS_MODES, MODE_SCHEDULED, QUERY_SOURCE_NEW, QUERY_SOURCE_SCHEDULED, QUERY_SOURCES

checkpointer = MemorySaver()
graph = build_graph(checkpointer)


class ScheduledThreadClosed(Exception):
    """A scheduled thread already has a run. Another analysis needs a new thread."""


def scheduled_thread_is_new(thread_id: str | None) -> bool:
    """Scheduled threads accept one run. A missing id is a new thread."""
    if not thread_id:
        return True
    return thread_is_empty(graph, thread_id)


def _drain(thread_id: str, messages: list, mode: str, response_type: str) -> None:
    """Run one graph pass. Node logs record the model and tool steps."""
    config = {"configurable": {"thread_id": thread_id}}
    for _chunk, _metadata in graph.stream(
        {
            "messages": messages,
            "tool_rounds": 0,
            "mode": mode,
            "response_type": response_type,
        },
        config=config,
        stream_mode="messages",
    ):
        pass


def _last_assistant(thread_id: str) -> AIMessage | None:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = graph.get_state(config)
    except Exception:
        return None
    values = snapshot.values if snapshot else {}
    messages = values.get("messages") if isinstance(values, dict) else None
    if not messages:
        return None
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def stream_turn(
    thread_id: str,
    log_file_path: str,
    user_query: str | None = None,
    mode: str = MODE_SCHEDULED,
    query_source: str = QUERY_SOURCE_NEW,
    scheduled_thread_id: str | None = None,
    response_type: str = "TEXT",
) -> Generator[dict, None, IssuesReported | None]:
    """
    Stream structured events:
      {"type": "token", "text": "..."}
      {"type": "done", "issues": ...|null}

    `mode` is MODE_SCHEDULED or MODE_QUERY.
    Scheduled runs ignore `user_query` and use the internal analysis instruction.
    A query with QUERY_SOURCE_SCHEDULED loads that scheduled thread's report into the first turn.
    response_type is TEXT or JSON. JSON is applied to the visible answer.
    """
    if mode not in ANALYSIS_MODES:
        raise ValueError(f"Invalid analysis mode: {mode}")
    if query_source not in QUERY_SOURCES:
        raise ValueError(f"Invalid query source: {query_source}")
    if response_type != "JSON":
        response_type = "TEXT"

    if mode == MODE_SCHEDULED:
        if not scheduled_thread_is_new(thread_id):
            raise ScheduledThreadClosed(SCHEDULED_THREAD_CLOSED)
        human_text = DEFAULT_SCHEDULED_QUERY
        query_source = QUERY_SOURCE_NEW
    elif thread_is_empty(graph, thread_id) and query_source == QUERY_SOURCE_SCHEDULED:
        human_text = query_with_scheduled_report(
            graph,
            scheduled_thread_id or "",
            user_query or DEFAULT_SCHEDULED_QUERY,
        )
    else:
        human_text = user_query if user_query else DEFAULT_SCHEDULED_QUERY

    new_messages: list[AnyMessage] = []
    if thread_is_empty(graph, thread_id):
        new_messages.append(
            SystemMessage(
                content=system_prompt_for(mode, log_file_path, query_source, response_type)
            )
        )
    new_messages.append(HumanMessage(content=human_text))

    config = {"configurable": {"thread_id": thread_id}}
    trace(
        "TURN start",
        thread=thread_id,
        mode=mode,
        response_type=response_type,
        query_source=query_source,
        scheduled_thread_id=scheduled_thread_id or "",
        query=human_text[:80],
        new_messages=len(new_messages),
    )

    _drain(thread_id, new_messages, mode, response_type)
    answer = _last_assistant(thread_id)
    answer_text = message_text(answer.content).strip() if answer else ""
    if answer is not None and narrated_tool_call(answer_text) and not has_tool_calls(answer):
        trace("TURN continue", thread=thread_id, reason="tool call was only text")
        _drain(
            thread_id,
            [HumanMessage(content=CONTINUE_AFTER_NARRATED_TOOL)],
            mode,
            response_type,
        )
        answer = _last_assistant(thread_id)
        answer_text = message_text(answer.content).strip() if answer else ""

    if answer is not None and has_tool_calls(answer):
        trace(
            "TURN incomplete",
            thread=thread_id,
            reason="stopped on a tool call",
            preview=answer_text or "(no text)",
        )
        answer_text = ""

    if not answer_text:
        answer_text = (
            "The agent finished without an answer. "
            "The model and tool steps are in agent.log."
        )
        trace("TURN empty", thread=thread_id)

    yield {"type": "token", "text": display_text(answer_text, response_type)}

    issues: IssuesReported | None = None
    try:
        snapshot = graph.get_state(config)
        values = snapshot.values if snapshot else {}
        raw_issues = values.get("issues") if isinstance(values, dict) else None
        if isinstance(raw_issues, IssuesReported):
            issues = raw_issues
    except Exception:
        issues = None

    trace(
        "TURN end",
        thread=thread_id,
        response_type=response_type,
        chars=len(answer_text),
        issues=len(issues.issues) if issues and issues.issues else 0,
        preview=answer_text[:160],
    )
    yield {"type": "done", "issues": issues.model_dump() if issues else None}
    return issues
