# Log Analyser Agent Development

*Date: October 7th, 2026*

Few changes that need to be implemented on different ends of the flow to make it more compatible with the Team Center

## Frontend Changes: 
2 seprate Pages for schdulded Analysis and query analysis

### Schdulded Analysis Page:
This page shall accept the file name / location, then do the schdulded analysis on the Logs of that perticular section.

- No query mode. 

### Query Analysis Page: 
This page shall accepet the file name and the query related to the logs and perfom the Analysis on the logs and provide the solution. 

## Agentic flow: 
These both should have different Prompts and a common flow and seprate backend APIs.

## ToDos Update
Need to update the prompts to make it more compatible with the Team Center.
- Set the output format, for the schdulded analysis for prompts.

- Work on the Log Fetching and Paging functionality and make it more robust.
- Remove the chat option from the schduled mode
- Look for better Agentic workflow for the task.
- 

## For Later
- Documentation Implementation via RAG to get better solution.
- RAG for saving the findings and referring them -> Brain / memory like structure.


---------------------

*Date: July 9th, 2026*

## Objective

Create a Agentic Workflow, where the Model analyses the logs and provides the insights and recommendations.

### Invocation
- Agent can be invoked using the User Query related to the logs. - There can be a query by the user. 
- Agent will also be invoked when the user is seeing the detailled logs. - No Query by the user.

## Tech Stack

- LangGraph (For Agentic Framework)
- Sonnet 4.6 (For LLM - Genric Purpose)
- Haiku (For LLM - Basic Query Refinement)
- Amazon Bedrock (Sourcing LLM)
- FastAPI* (For API Exposure )
- Streamlit* (For UI Exposure)
- ChromaDB* (VectorDB for RAG operations)

### Approach
Creating a class based code structure, and integrate it with LangChain Runnable, to create a Agentic Workflow.
Using classes for better scaleability and maintainability. This shall allow us to reuse the same components again and again.

_* Optional, Used only when if Required, These can also be updated as per the project requirements_

## Ideas
- Model can provide 2 types of recommendations
  1. General Recommendations related to the logs, without having project specific details
  2. Specific Recommendations related to the project specific details like, how to improve the performance of the project, how to improve the security of the project, how to improve the scalability of the project, etc.<br>
    This Can be toggled on and off by the user, based on the project specific details. regarding the project  providing the files and documentations (this can be fetched if publically available).  
    Use RAG to get the perticular Docs and generate the recomendation accordingly.
    
- Create a class for Reterieval and filtering the logs. This should have following:
  - Listing all the logs files and filtering out the requried and not requried log files
  - Fetching latest logs from a given file
  - Paging the logs and fetching older logs from a file. 

- Create a class for Docuentation Reterieval. 
  - Can use sematic serach for the doc reterieval. 
    - can also be keyword search + Reranking - If required not sure on this.

- Should Use Chaining workflows.

- Need to Create a seprate repo for storing the prompts. Requrired Prompts:
  - System Prompt
  - Prompt for general recommendations
  - Prompt for specific recommendations
  - Prompt for Query Refinement

