# This is a basic log agent that uses the LangChain framework to analyze logs.
# uses LangChain to create a chain using template, llm and parser only (no LangGraph workflow)

from time import time
from datetime import datetime

from langchain_aws import ChatBedrockConverse
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from Resources.log_resources import LogResources
from Prompts.SystemPrompts import LogsAnalyzerSystemPrompt

from dotenv import load_dotenv
load_dotenv()

llm_config = {
    'model': "us.anthropic.claude-sonnet-4-6",
    'region_name': "us-east-1"
}

template = ChatPromptTemplate.from_messages([
    ("system", LogsAnalyzerSystemPrompt),
    ("human", "Give me details about the issues found in these logs: {logs}"),
])
llm = ChatBedrockConverse(**llm_config)
parser = StrOutputParser()

chain = template | llm | parser

if __name__ == "__main__":
    LogFetcher = LogResources(r'logs\LOGS_POOL_DUMP\PoolServer1') 
    # logs = LogFetcher.fetch_logs_from_file("ServerManager.log", limit=20)
    logs = LogFetcher.fetch_logs_from_file("ServerManager.log", 
        start_time = datetime.strptime('2024/07/14-20:35:34,479 UTC', "%Y/%m/%d-%H:%M:%S,%f UTC"), 
        end_time = datetime.strptime('2024/07/15-05:07:19,510 UTC', "%Y/%m/%d-%H:%M:%S,%f UTC")
    )
    
    print(len(logs))
    
    start_time = time()
    result = chain.invoke({"logs": logs})
    end_time = time()
    print(result)
    print(f"Time taken to generate respone: {end_time - start_time} seconds")

    with open("result.md", "w", encoding="utf-8") as f:
        f.write(result)
