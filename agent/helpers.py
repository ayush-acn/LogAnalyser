"""Support code for the graph nodes and a single analysis turn."""

from __future__ import annotations

import json

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode

from agent.formatting import issues_to_message, message_text
from agent.prompts import (
    LogsAnalyzerSystemPrompt,
    UserLogQuerySystemPrompt,
    UserScheduledQuerySystemPrompt,
)
from agent.schemas import IssuesReported
from agent.state import FlowState
from agent.tracing import trace
from config import (
    MODE_QUERY,
    MODE_SCHEDULED,
    QUERY_SOURCE_SCHEDULED,
    REPO_ROOT,
    main_llm_config,
    thread_timestamp,
    tool_llm_config,
)
from tools import LOG_TOOLS

llm = ChatBedrockConverse(**main_llm_config)
main_llm = ChatBedrockConverse(**main_llm_config).with_structured_output(IssuesReported)
tool_llm = ChatBedrockConverse(**tool_llm_config).bind_tools(LOG_TOOLS)
log_tool_node = ToolNode(LOG_TOOLS)

ANSWER_NOW = (
    "Tool budget is used up. Do not call tools. Answer the user now from the logs "
    "already fetched. Say what is still unknown."
)
CONTINUE_AFTER_NARRATED_TOOL = (
    "Your last message only described a tool call. That text does not run a tool. "
    "Use log_overview, search_logs, or get_context, then answer the user. "
    "Those are the only tools. Do not invent a tool name and do not write [Called ...]."
)
JSON_QUERY_INSTRUCTION = """
# Output
- When you answer the user, return one JSON object and nothing else.
- Shape: {"answer": "short explanation", "actions": ["next step"]}
- Tool calls stay normal tool calls. Do not put a tool call inside the JSON.
"""
STRUCTURE_NOW = (
    "Structure the findings from the conversation above into the required issue report."
)
DEFAULT_SCHEDULED_QUERY = "Analyse the log file and report the problems."
SCHEDULED_THREAD_CLOSED = (
    "Scheduled analysis already ran on this thread. "
    "Start a new thread for another analysis."
)
SCHEDULED_REPORT_MISSING = "No scheduled report was found for that thread."

DOCS_GRAPH_PNG = REPO_ROOT / "docs" / "graph.png"
DOCS_GRAPH_MERMAID = REPO_ROOT / "docs" / "graph.mmd"


def mode_of(state: FlowState) -> str:
    return MODE_QUERY if state.get("mode") == MODE_QUERY else MODE_SCHEDULED


def is_query(state: FlowState) -> bool:
    return mode_of(state) == MODE_QUERY


def tool_rounds(state: FlowState) -> int:
    return int(state.get("tool_rounds") or 0)


def thread_id_from(config: RunnableConfig) -> str:
    return str((config.get("configurable") or {}).get("thread_id", ""))


def has_tool_calls(message: AnyMessage) -> bool:
    if getattr(message, "tool_calls", None):
        return True
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return False
    return any(
        isinstance(block, dict) and block.get("type") in {"tool_use", "tool_call"}
        for block in content
    )


def tool_names(message: AnyMessage) -> str:
    tool_calls = getattr(message, "tool_calls", None) or []
    return ", ".join(call.get("name", "?") for call in tool_calls) or "none"


def tool_call_detail(message: AnyMessage) -> str:
    """Tool name plus a short argument preview for the log."""
    tool_calls = getattr(message, "tool_calls", None) or []
    if not tool_calls:
        return "none"
    parts: list[str] = []
    for call in tool_calls:
        args = json.dumps(call.get("args") or {}, default=str, ensure_ascii=False)
        if len(args) > 180:
            args = args[:180] + "..."
        parts.append(f"{call.get('name', '?')} {args}")
    return " || ".join(parts)


def narrated_tool_call(text: str) -> bool:
    """True when the model wrote a tool call as text instead of calling one."""
    sample = " ".join(text.split())
    return "[Called " in sample and "parameters" in sample


def display_text(text: str, response_type: str) -> str:
    """Fence JSON so the chat shows it as a block. The checkpoint keeps the raw text."""
    if response_type != "JSON":
        return text
    stripped = text.strip()
    if not stripped.startswith(("{", "[")):
        return text
    return f"```json\n{stripped}\n```"


def ensure_user_turn(messages: list[AnyMessage], nudge: str) -> list[AnyMessage]:
    """Bedrock Converse requires the conversation to end with a user message."""
    last = messages[-1] if messages else None
    if isinstance(last, HumanMessage):
        return messages
    return messages + [HumanMessage(content=nudge)]


def system_prompt_for(
    mode: str,
    log_file_path: str,
    query_source: str,
    response_type: str = "TEXT",
) -> str:
    if mode != MODE_QUERY:
        prompt = LogsAnalyzerSystemPrompt.format(file_path=log_file_path)
    elif query_source == QUERY_SOURCE_SCHEDULED:
        prompt = UserScheduledQuerySystemPrompt.format(file_path=log_file_path)
    else:
        prompt = UserLogQuerySystemPrompt.format(file_path=log_file_path)
    if mode == MODE_QUERY and response_type == "JSON":
        prompt = prompt.rstrip() + "\n" + JSON_QUERY_INSTRUCTION
    return prompt


def thread_is_empty(compiled, thread_id: str) -> bool:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = compiled.get_state(config)
        values = snapshot.values if snapshot else {}
        messages = values.get("messages") if isinstance(values, dict) else None
        return not messages
    except Exception:
        return True


def scheduled_report_text(compiled, thread_id: str) -> str:
    """Report text saved on a scheduled thread. Raises when that thread has none."""
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = compiled.get_state(config)
        values = snapshot.values if snapshot else {}
    except Exception as exc:
        raise ValueError(SCHEDULED_REPORT_MISSING) from exc
    if not isinstance(values, dict):
        raise ValueError(SCHEDULED_REPORT_MISSING)

    messages = values.get("messages") or []
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not has_tool_calls(message):
            text = message_text(message.content).strip()
            if text:
                return text

    issues = values.get("issues")
    if isinstance(issues, IssuesReported):
        return message_text(issues_to_message(issues).content).strip()
    raise ValueError(SCHEDULED_REPORT_MISSING)


def query_with_scheduled_report(compiled, scheduled_thread_id: str, question: str) -> str:
    report = scheduled_report_text(compiled, scheduled_thread_id)
    when = thread_timestamp(scheduled_thread_id) or "unknown time"
    return (
        f"Scheduled report ({scheduled_thread_id}, {when}):\n"
        f"{report}\n\n"
        f"Question:\n{question}"
    )


def query_answer(messages: list[AnyMessage]) -> AIMessage:
    """Answer with the tool-bound model so Bedrock still accepts earlier tool blocks.

    Any further tool call is dropped. The user gets the text answer instead.
    """
    invoke_messages = ensure_user_turn(messages, ANSWER_NOW)
    response = tool_llm.invoke(invoke_messages)
    text = message_text(response.content).strip()
    if has_tool_calls(response):
        if not text:
            text = (
                "The tool budget is used up, and there is no further log text to add. "
                "What is still unknown should be asked as a narrower question."
            )
        return AIMessage(content=text)
    if not isinstance(response, AIMessage):
        return AIMessage(content=str(response))
    return response


def save_graph_diagram(compiled) -> None:
    """Write the compiled graph under docs/. Remove the call before production deploy."""
    view = compiled.get_graph()
    DOCS_GRAPH_MERMAID.parent.mkdir(parents=True, exist_ok=True)
    DOCS_GRAPH_MERMAID.write_text(view.draw_mermaid(), encoding="utf-8")
    try:
        view.draw_mermaid_png(output_file_path=str(DOCS_GRAPH_PNG), max_retries=1, retry_delay=0.2)
    except Exception as exc:
        trace("GRAPH diagram", png="skipped", reason=exc)
