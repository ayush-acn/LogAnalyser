from langgraph.graph import END, START, StateGraph

from agent.helpers import save_graph_diagram
from agent.nodes import orch_node, resp_node, route_after_orch, route_after_tools, tools_node
from agent.state import FlowState


def build_graph(memory_checkpointer):
    builder = StateGraph(FlowState)
    builder.add_node("orch", orch_node)
    builder.add_node("tools", tools_node)
    builder.add_node("resp", resp_node)

    builder.add_edge(START, "orch")
    builder.add_conditional_edges(
        "orch",
        route_after_orch,
        {"tools": "tools", "resp": "resp", END: END},
    )
    builder.add_conditional_edges(
        "tools",
        route_after_tools,
        {"orch": "orch", "resp": "resp"},
    )
    builder.add_edge("resp", END)
    compiled = builder.compile(checkpointer=memory_checkpointer)
    # Local documentation only. Remove this call before production deploy.
    save_graph_diagram(compiled)
    return compiled
