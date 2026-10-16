from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END

from agent.formatting import issues_to_message, message_text
from agent.helpers import (
    STRUCTURE_NOW,
    ensure_user_turn,
    has_tool_calls,
    is_query,
    log_tool_node,
    main_llm,
    mode_of,
    query_answer,
    thread_id_from,
    tool_call_detail,
    tool_llm,
    tool_names,
    tool_rounds,
)
from agent.state import FlowState
from agent.tracing import trace
from config import DEFAULT_MAX_TOOL_ROUNDS, main_llm_config, tool_llm_config


def orch_node(state: FlowState, config: RunnableConfig) -> FlowState:
    messages = list(state.get("messages", []))
    rounds = tool_rounds(state)
    trace(
        "MODEL call",
        node="orch",
        model=tool_llm_config["model"],
        thread=thread_id_from(config),
        message_count=len(messages),
        tool_rounds=rounds,
    )
    response = tool_llm.invoke(messages)
    preview = message_text(response.content).strip()
    trace(
        "MODEL response",
        node="orch",
        tool_calls=tool_call_detail(response) if has_tool_calls(response) else "none",
        tool_rounds=rounds,
        preview=preview or "(no text)",
    )
    return {"messages": [response]}


def route_after_orch(state: FlowState, config: RunnableConfig) -> str:
    """Send tool calls back to the tools. Query answers end here; scheduled answers go to resp."""
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    mode = mode_of(state)
    rounds = tool_rounds(state)

    if last is not None and has_tool_calls(last) and rounds < DEFAULT_MAX_TOOL_ROUNDS:
        trace("ROUTE", from_node="orch", to="tools", mode=mode, tool_calls=tool_names(last))
        return "tools"
    if is_query(state):
        # Query answers come from orch. Do not send that AIMessage into resp:
        # Bedrock Converse rejects a conversation that ends on an assistant message.
        trace("ROUTE", from_node="orch", to="END", mode=mode, reason="query final answer")
        return END
    trace("ROUTE", from_node="orch", to="resp", mode=mode, reason="scheduled structuring")
    return "resp"


def tools_node(state: FlowState, config: RunnableConfig) -> FlowState:
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    rounds = tool_rounds(state)
    trace(
        "TOOL call",
        node="tools",
        thread=thread_id_from(config),
        tools=tool_call_detail(last) if last else "none",
        tool_rounds=rounds,
    )
    try:
        result = log_tool_node.invoke(state)
    except Exception as exc:
        trace("TOOL failed", node="tools", error=exc)
        raise
    for message in result.get("messages", []):
        if isinstance(message, ToolMessage):
            trace(
                "TOOL result",
                name=getattr(message, "name", "") or "tool",
                chars=len(message_text(message.content)),
            )
    trace("TOOL response", node="tools", tool_rounds=rounds + 1)
    return {
        "messages": result.get("messages", []),
        "tool_rounds": rounds + 1,
    }


def route_after_tools(state: FlowState, config: RunnableConfig) -> str:
    rounds = tool_rounds(state)
    mode = mode_of(state)
    if rounds >= DEFAULT_MAX_TOOL_ROUNDS:
        trace("ROUTE", from_node="tools", to="resp", mode=mode, reason="tool budget")
        return "resp"
    trace("ROUTE", from_node="tools", to="orch", mode=mode, tool_rounds=rounds)
    return "orch"


def resp_node(state: FlowState, config: RunnableConfig) -> FlowState:
    messages = list(state.get("messages", []))
    mode = mode_of(state)

    if is_query(state):
        trace(
            "MODEL call",
            node="resp",
            model=tool_llm_config["model"],
            mode=mode,
            output="chat",
            thread=thread_id_from(config),
            message_count=len(messages),
        )
        response = query_answer(messages)
        trace("MODEL response", node="resp", mode=mode, output="chat")
        return {"messages": [response], "issues": None}

    invoke_messages = ensure_user_turn(messages, STRUCTURE_NOW)
    trace(
        "MODEL call",
        node="resp",
        model=main_llm_config["model"],
        mode=mode,
        output="IssuesReported",
        thread=thread_id_from(config),
        message_count=len(invoke_messages),
    )
    reported = main_llm.invoke(invoke_messages)
    issue_count = len(reported.issues) if reported and reported.issues else 0
    trace(
        "MODEL response",
        node="resp",
        mode=mode,
        output="IssuesReported",
        issues_found=issue_count,
    )
    as_json = state.get("response_type") == "JSON"
    return {
        "messages": [issues_to_message(reported, as_json=as_json)],
        "issues": reported,
    }
