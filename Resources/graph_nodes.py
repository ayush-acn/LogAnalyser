from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import ToolMessage
from langchain_aws import ChatBedrockConverse

from config import tool_llm_config, main_llm_config
from Resources.graph_state import FlowState
from Tools.log_tools import log_fetch_tools
from Models.log_agent import IssuesReported
from Resources.utils import _parse_tool_logs, issues_to_message


main_llm = ChatBedrockConverse(**main_llm_config).with_structured_output(IssuesReported)
tool_llm = ChatBedrockConverse(**tool_llm_config).bind_tools(log_fetch_tools)

log_tool_node = ToolNode(log_fetch_tools)

def orch_node(state: FlowState) -> FlowState:
    messages = state.get('messages', '')
    response = tool_llm.invoke(messages)
    return {'messages': [response]}

def tools_node(state: FlowState) -> FlowState:
    result = log_tool_node.invoke(state)
    fetched_logs: list[dict] = []
    for message in result.get('messages', []):
        if isinstance(message, ToolMessage):
            fetched_logs.extend(_parse_tool_logs(message.content))
    return {
        'messages': result.get('messages', []),
        'logs': fetched_logs,
    }

def resp_node(state: FlowState) -> FlowState:
    messages = state.get('messages', '')
    reported = main_llm.invoke(messages)
    return {
        'messages': [issues_to_message(reported)],
        'issues': reported,
    }