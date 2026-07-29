from typing import List

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, AnyMessage

from langgraph.checkpoint.memory import MemorySaver
from Resources.graph import build_graph
from Resources.utils import message_text, trace
from Prompts.SystemPrompts import LogsAnalyzerSystemPrompt, UserLogQuerySystemPrompt
from dotenv import load_dotenv
load_dotenv()

checkpointer = MemorySaver()
graph = build_graph(checkpointer)

# log_file_path = r'C:\Data\Project\ASBG\LogAnalyser\logs\LOGS_POOL_DUMP\PoolServer1\ServerManager.log'
def new_chat(log_file_path: str, user_query: str | None = None):
    '''
    This function is used to be called only when the new chat is being created, to generate the system message for the chat.
    '''
    if user_query:
        system_message = UserLogQuerySystemPrompt.format(file_path = log_file_path)
    else:
        system_message = LogsAnalyzerSystemPrompt.format(file_path = log_file_path)
    return system_message


def stream_messages(messages: List[AnyMessage], thread_id: str, log_file_path: str, user_query: str| None = None):
    '''
    This function is a generator that streams messages from the graph. This only used when there is user query. 
    '''

    default_query = 'Please analyse the latest logs from the file.'

    # With a checkpointer, only send *new* messages each turn. Re-sending the
    # full frontend history would duplicate everything already stored in state.
    new_messages: List[AnyMessage] = []
    if len(messages) == 0:
        system_message = SystemMessage(content=new_chat(log_file_path, user_query))
        messages.append(system_message)
        new_messages.append(system_message)

    human_message = HumanMessage(content=user_query if user_query else default_query)
    messages.append(human_message)
    new_messages.append(human_message)

    config = {'configurable': {'thread_id': thread_id}}

    trace(
        'TURN start',
        thread=thread_id,
        query=(user_query or default_query)[:80],
        new_messages=len(new_messages),
    )

    # Orch may stream text before tool_calls appear on later chunks. Buffer orch
    # text and only emit it when the turn never produced a resp answer.
    orch_parts: list[str] = []
    resp_emitted = False

    for chunk, metadata in graph.stream(
        {'messages': new_messages},
        config=config,
        stream_mode='messages',
    ):
        if not isinstance(chunk, AIMessage):
            continue

        node = metadata.get('langgraph_node')
        if node not in ('resp', 'orch'):
            continue

        if getattr(chunk, 'tool_calls', None):
            orch_parts.clear()
            continue

        text = message_text(chunk.content)
        if not text:
            continue

        if node == 'resp':
            resp_emitted = True
            yield text
        else:
            orch_parts.append(text)

    if not resp_emitted:
        for text in orch_parts:
            yield text

    trace(
        'TURN end',
        thread=thread_id,
        source='resp' if resp_emitted else 'orch',
    )
