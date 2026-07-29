from langgraph.graph import StateGraph, START, END
from Resources.graph_nodes import orch_node, tools_node, resp_node
from langgraph.prebuilt import tools_condition
from Resources.graph_state import FlowState

def build_graph(memory_checkpointer):
    builder = StateGraph(FlowState)
    builder.add_node('orch', orch_node)
    builder.add_node('tools', tools_node)
    builder.add_node('resp', resp_node)

    builder.add_edge(START, 'orch')
    builder.add_conditional_edges('orch', tools_condition, ['tools', 'resp'])
    builder.add_edge('tools', 'resp')
    builder.add_edge('resp', END)

    graph = builder.compile(checkpointer = memory_checkpointer)
    return graph