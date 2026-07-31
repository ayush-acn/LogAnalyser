from __future__ import annotations

from typing import Generator, Iterator

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver

from Models.log_agent import IssuesReported
from Prompts.SystemPrompts import LogsAnalyzerSystemPrompt, UserLogQuerySystemPrompt
from Resources.graph import build_graph
from Resources.utils import message_text, trace
from dotenv import load_dotenv

load_dotenv()

checkpointer = MemorySaver()
graph = build_graph(checkpointer)

DEFAULT_SCHEDULED_QUERY = "Please analyse the latest logs from the file."


def new_chat(log_file_path: str, user_query: str | None = None) -> str:
    if user_query:
        return UserLogQuerySystemPrompt.format(file_path=log_file_path)
    return LogsAnalyzerSystemPrompt.format(file_path=log_file_path)


def stream_messages(
    messages: list[AnyMessage],
    thread_id: str,
    log_file_path: str,
    user_query: str | None = None,
) -> Generator[str, None, None]:
    """Stream assistant text tokens for a turn (query or scheduled)."""
    for event in stream_turn(messages, thread_id, log_file_path, user_query):
        if event.get("type") == "token":
            yield event["text"]


def stream_turn(
    messages: list[AnyMessage],
    thread_id: str,
    log_file_path: str,
    user_query: str | None = None,
) -> Generator[dict, None, IssuesReported | None]:
    """
    Stream structured events:
      {"type": "token", "text": "..."}
      {"type": "done"}
    Returns IssuesReported (scheduled) via generator return value.
    """
    default_query = DEFAULT_SCHEDULED_QUERY
    new_messages: list[AnyMessage] = []
    if len(messages) == 0:
        system_message = SystemMessage(content=new_chat(log_file_path, user_query))
        messages.append(system_message)
        new_messages.append(system_message)

    human_message = HumanMessage(content=user_query if user_query else default_query)
    messages.append(human_message)
    new_messages.append(human_message)

    config = {"configurable": {"thread_id": thread_id}}
    trace(
        "TURN start",
        thread=thread_id,
        query=(user_query or default_query)[:80],
        new_messages=len(new_messages),
    )

    orch_parts: list[str] = []
    resp_emitted = False

    for chunk, metadata in graph.stream(
        {"messages": new_messages, "tool_rounds": 0},
        config=config,
        stream_mode="messages",
    ):
        if not isinstance(chunk, AIMessage):
            continue

        node = metadata.get("langgraph_node")
        if node not in ("resp", "orch"):
            continue

        if getattr(chunk, "tool_calls", None):
            orch_parts.clear()
            continue

        text = message_text(chunk.content)
        if not text:
            continue

        if node == "resp":
            resp_emitted = True
            yield {"type": "token", "text": text}
        else:
            orch_parts.append(text)

    if not resp_emitted:
        for text in orch_parts:
            yield {"type": "token", "text": text}

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
        source="resp" if resp_emitted else "orch",
        issues=len(issues.issues) if issues and issues.issues else 0,
    )
    yield {"type": "done", "issues": issues.model_dump() if issues else None}
    return issues
