from typing import Annotated, List, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from agent.schemas import IssuesReported


class FlowState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    issues: IssuesReported | None
    tool_rounds: int
    # "query" or "scheduled". Set by the API on every turn.
    mode: str
    # "TEXT" or "JSON". Set by the API on every turn.
    response_type: str
