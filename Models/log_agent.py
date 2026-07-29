from pydantic import BaseModel, Field
from typing import List

class IssueReport(BaseModel):
    category: str = Field(description = 'Category of the issue. It can be one of the following: Bug, Performance Issue, Security Issue, Others, etc. The category should be determined based on the nature of the issue and its impact on the system.')
    priority: str = Field(description = 'Priority of the issue. It can be one of the following: P1, P2, P3, P4. Where P1 is the highest priority and P4 is the lowest priority. The priority should be determined based on the severity of the issue and its impact on the system.')
    issue: str = Field(description = 'A brief description of the issue. It should provide enough information to understand the nature of the problem and its impact on the system. No need to include the machine name or timestamp in this field, as they are provided separately.')
    generic_recommendation: str | None = Field(description = 'A generic recommendation for addressing the issue. It should provide a high-level suggestion for resolving the problem, without going into specific implementation details.')
    specific_recommendation: str | None = Field(description = 'A specific recommendation for addressing the issue. It should only be provided if there is mention of the solution in the docs provided else None.', default = None)
    solution_steps: List[str] | None = Field(description = 'A list of specific steps in order to implement the solution. It should only be provided if there is mention of the solution in the docs provided else None.', default = None)
    timestamp: str | None = Field(description = 'The timestamp of the log entry that triggered the issue. It should be in the format YYYY-MM-DD HH:MM:SS, and it should provide context for when the issue occurred.', default = None)
    machine: str | None = Field(description = 'The machine or server where the issue was detected. It should provide context for where the problem occurred, which can be useful for troubleshooting and resolving the issue.', default = None)

class IssuesReported(BaseModel):
    issues: List[IssueReport] = Field(description = 'A list of issues reported. Each issue should be represented as an instance of the IssueReport model, providing detailed information about the issue, its category, priority, and recommendations for resolution.')