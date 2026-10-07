from __future__ import annotations

from typing import Generator

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
ANALYSIS_MODES = ("query", "scheduled")


def system_prompt_for(mode: str, log_file_path: str) -> str:
    if mode == "query":
        return UserLogQuerySystemPrompt.format(file_path=log_file_path)
    return LogsAnalyzerSystemPrompt.format(file_path=log_file_path)


def _is_new_thread(thread_id: str) -> bool:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = graph.get_state(config)
        values = snapshot.values if snapshot else {}
        messages = values.get("messages") if isinstance(values, dict) else None
        return not messages
    except Exception:
        return True


def stream_turn(
    thread_id: str,
    log_file_path: str,
    user_query: str | None = None,
    mode: str = "scheduled",
) -> Generator[dict, None, IssuesReported | None]:
    """
    Stream structured events:
      {"type": "token", "text": "..."}
      {"type": "done", "issues": ...|null}

    `mode` selects the route: "query" or "scheduled".
    The system prompt is attached only on the first turn of a thread.
    """
    if mode not in ANALYSIS_MODES:
        raise ValueError(f"Invalid analysis mode: {mode}")

    default_query = DEFAULT_SCHEDULED_QUERY
    human_text = user_query if user_query else default_query
    new_messages: list[AnyMessage] = []
    if _is_new_thread(thread_id):
        new_messages.append(
            SystemMessage(content=system_prompt_for(mode, log_file_path))
        )
    new_messages.append(HumanMessage(content=human_text))

    config = {"configurable": {"thread_id": thread_id}}
    trace(
        "TURN start",
        thread=thread_id,
        mode=mode,
        query=human_text[:80],
        new_messages=len(new_messages),
    )

    orch_parts: list[str] = []
    resp_emitted = False

    for chunk, metadata in graph.stream(
        {"messages": new_messages, "tool_rounds": 0, "mode": mode},
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
