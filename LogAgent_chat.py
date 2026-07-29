import json
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, AnyMessage
from langchain_core.prompts import ChatPromptTemplate


from langgraph.checkpoint.memory import MemorySaver
from Resources.graph import build_graph
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
    
    if len(messages) == 0:
        messages.append(SystemMessage(content = new_chat(log_file_path, user_query)))

    messages.append(HumanMessage(content = user_query if user_query else default_query))
    config = {'configurable': {'thread_id': thread_id}}
    
    AIresp = ''
    for chunk, metadata in graph.stream(
        {'messages': messages},
        config = config,
        stream_mode = 'messages'
    ):
       if (
            metadata.get('langgraph_node') == 'resp'
            and isinstance(chunk, AIMessage)
            and isinstance(chunk.content, str)
            and chunk.content
        ):
            AIresp += chunk.content
            yield chunk.content
    






# if __name__ == '__main__':
#     # user_message = f"Can you analyse the logs from 6:30 to 8:00 on 2024-07-15? Logfilepath : {log_file_path}"
#     resp = ''
#     for chunk in stream_messages(user_message):
#         resp+=str(chunk)
#         print(chunk, end = '')

#     # print(resp)


# response = graph.invoke({
#     'messages': [
#         SystemMessage(content = f"The log file path is {log_file_path}"),
#         HumanMessage(content = "Can you analyse the logs from 6:30 to 8:00 on 2024-07-15?")
#     ]
# }, config = {'configurable': {'thread_id': thread_id}})

# # 
# from pprint import pprint
# print(response)
# with open(f'Results/chatflow_{thread_id}.json', 'w') as f:
#     f.write(json.dumps(response['issues'].model_dump(), indent = 2))