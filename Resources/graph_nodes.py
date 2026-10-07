from langgraph.prebuilt import ToolNode
from langgraph.graph import END
from langchain_core.messages import ToolMessage, AIMessage, HumanMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langchain_aws import ChatBedrockConverse

from config import tool_llm_config, main_llm_config, DEFAULT_MAX_TOOL_ROUNDS
from Resources.graph_state import FlowState
from Tools.log_tools import log_fetch_tools
from Models.log_agent import IssuesReported
from Resources.utils import _parse_tool_logs, issues_to_message, message_text, trace

llm = ChatBedrockConverse(**main_llm_config)
main_llm = ChatBedrockConverse(**main_llm_config).with_structured_output(IssuesReported)
tool_llm = ChatBedrockConverse(**tool_llm_config).bind_tools(log_fetch_tools)

log_tool_node = ToolNode(log_fetch_tools)


def _mode(state: FlowState) -> str:
    '''Route stored on the graph state by the API: query or scheduled.'''
    return 'query' if state.get('mode') == 'query' else 'scheduled'


def _is_query(state: FlowState) -> bool:
    return _mode(state) == 'query'


def _thread_id(config: RunnableConfig) -> str:
    return str((config.get('configurable') or {}).get('thread_id', ''))


def _has_tool_calls(message: AnyMessage) -> bool:
    return bool(getattr(message, 'tool_calls', None))


def _tool_names(message: AnyMessage) -> str:
    tool_calls = getattr(message, 'tool_calls', None) or []
    return ', '.join(call.get('name', '?') for call in tool_calls) or 'none'


def orch_node(state: FlowState, config: RunnableConfig) -> FlowState:
    messages = list(state.get('messages', []))
    rounds = int(state.get('tool_rounds') or 0)

    # Soft safeguard: nudge the model to answer with what it has.
    if rounds >= DEFAULT_MAX_TOOL_ROUNDS:
        messages = messages + [
            HumanMessage(
                content=(
                    f'Tool-round safeguard reached ({DEFAULT_MAX_TOOL_ROUNDS}). '
                    'Do not call more tools. Answer now using the log data already fetched.'
                )
            )
        ]

    trace(
        'MODEL call',
        node='orch',
        model=tool_llm_config['model'],
        thread=_thread_id(config),
        message_count=len(messages),
        tool_rounds=rounds,
    )

    # After safeguard, bind with no tools so the model must answer.
    if rounds >= DEFAULT_MAX_TOOL_ROUNDS:
        response = ChatBedrockConverse(**tool_llm_config).invoke(messages)
    else:
        response = tool_llm.invoke(messages)

    if _has_tool_calls(response):
        trace(
            'MODEL response',
            node='orch',
            tool_calls=_tool_names(response),
            tool_rounds=rounds,
        )
    else:
        trace('MODEL response', node='orch', tool_calls='none', tool_rounds=rounds)
    return {'messages': [response]}


def route_after_orch(state: FlowState, config: RunnableConfig) -> str:
    '''
    Route orch output: tools when tool_calls present (and under safeguard),
    else END for query final answers, or resp for scheduled structuring.
    '''
    messages = state.get('messages', [])
    last = messages[-1] if messages else None
    mode = _mode(state)
    rounds = int(state.get('tool_rounds') or 0)

    if (
        last is not None
        and _has_tool_calls(last)
        and rounds < DEFAULT_MAX_TOOL_ROUNDS
    ):
        trace('ROUTE', from_node='orch', to='tools', mode=mode, tool_calls=_tool_names(last))
        return 'tools'
    if _is_query(state):
        # Query answers come from orch. Do not send orch's AIMessage into resp:
        # Bedrock Converse rejects assistant-prefill (conversation must end
        # with a user message). Empty timed windows are a valid orch answer.
        trace('ROUTE', from_node='orch', to='END', mode=mode, reason='query final answer')
        return END
    trace('ROUTE', from_node='orch', to='resp', mode=mode, reason='scheduled structuring')
    return 'resp'


def tools_node(state: FlowState, config: RunnableConfig) -> FlowState:
    messages = state.get('messages', [])
    last = messages[-1] if messages else None
    rounds = int(state.get('tool_rounds') or 0)
    trace(
        'TOOL call',
        node='tools',
        thread=_thread_id(config),
        tools=_tool_names(last) if last else 'none',
        tool_rounds=rounds,
    )
    result = log_tool_node.invoke(state)
    fetched_logs: list[dict] = []
    for message in result.get('messages', []):
        if isinstance(message, ToolMessage):
            fetched_logs.extend(_parse_tool_logs(message.content))
    trace(
        'TOOL response',
        node='tools',
        log_entries=len(fetched_logs),
        tool_rounds=rounds + 1,
    )
    return {
        'messages': result.get('messages', []),
        'logs': fetched_logs,
        'tool_rounds': rounds + 1,
    }


def route_after_tools(state: FlowState, config: RunnableConfig) -> str:
    '''After tools, return to orch for another fetch round, or resp when done/cap.'''
    rounds = int(state.get('tool_rounds') or 0)
    mode = _mode(state)
    if rounds >= DEFAULT_MAX_TOOL_ROUNDS:
        trace('ROUTE', from_node='tools', to='resp', mode=mode, reason='safeguard')
        return 'resp'
    trace('ROUTE', from_node='tools', to='orch', mode=mode, tool_rounds=rounds)
    return 'orch'


def _ensure_user_turn(messages: list[AnyMessage], nudge: str) -> list[AnyMessage]:
    '''Bedrock Converse requires the conversation to end with a user message.'''
    last = messages[-1] if messages else None
    if isinstance(last, HumanMessage):
        return messages
    return messages + [HumanMessage(content=nudge)]


def resp_node(state: FlowState, config: RunnableConfig) -> FlowState:
    messages = list(state.get('messages', []))
    mode = _mode(state)

    if _is_query(state):
        last = messages[-1] if messages else None
        # Prefer the orch answer when it already finalized after tools.
        if (
            isinstance(last, AIMessage)
            and not _has_tool_calls(last)
            and message_text(last.content).strip()
        ):
            trace(
                'MODEL response',
                node='resp',
                mode=mode,
                output='chat',
                reason='reuse orch answer',
            )
            return {'messages': [], 'issues': None}

        invoke_messages = _ensure_user_turn(
            messages,
            'Based on the tool results above, answer the user question now. '
            'If no logs matched the requested time window, say so clearly.',
        )
        trace(
            'MODEL call',
            node='resp',
            model=main_llm_config['model'],
            mode=mode,
            output='chat',
            thread=_thread_id(config),
            message_count=len(invoke_messages),
        )
        response = llm.invoke(invoke_messages)
        if not isinstance(response, AIMessage):
            response = AIMessage(content=str(response))
        trace('MODEL response', node='resp', mode=mode, output='chat')
        return {
            'messages': [response],
            'issues': None,
        }

    invoke_messages = _ensure_user_turn(
        messages,
        'Please structure the findings from the conversation above '
        'into the required issue report format.',
    )
    nudged = len(invoke_messages) != len(messages)

    trace(
        'MODEL call',
        node='resp',
        model=main_llm_config['model'],
        mode=mode,
        output='IssuesReported',
        thread=_thread_id(config),
        message_count=len(invoke_messages),
        nudged=nudged,
    )
    reported = main_llm.invoke(invoke_messages)
    issue_count = len(reported.issues) if reported.issues else 0
    trace(
        'MODEL response',
        node='resp',
        mode=mode,
        output='IssuesReported',
        issues_found=issue_count,
    )
    return {
        'messages': [issues_to_message(reported)],
        'issues': reported,
    }
