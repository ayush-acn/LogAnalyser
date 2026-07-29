from typing import Annotated, TypedDict, List
from operator import add

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from Models.log_agent import IssuesReported

class FlowState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    logs: Annotated[List[dict], add]
    issues: IssuesReported | None