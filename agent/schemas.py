from typing import List, Literal

from pydantic import BaseModel, Field

Category = Literal[
    "Bug",
    "Performance",
    "Security",
    "Availability",
    "Configuration",
    "Other",
]
Priority = Literal["P1", "P2", "P3", "P4"]


class IssueCitation(BaseModel):
    file_path: str = Field(
        description="Absolute path copied from a tool output header (== path ==). Do not guess."
    )
    line_number: int = Field(
        description="1-based line number copied from the L prefix in tool output. Do not invent this number."
    )


class IssueReport(BaseModel):
    category: Category = Field(description="Kind of issue. Use Other when none of the named kinds fit.")
    priority: Priority = Field(
        description="P1 is the highest priority and P4 is the lowest. Base this on severity and impact."
    )
    issue: str = Field(
        description="A short description of the problem. Leave out the machine name and timestamp."
    )
    generic_recommendation: str | None = Field(
        description="A high-level suggestion for resolving the problem, without implementation detail."
    )
    timestamp: str | None = Field(
        default=None,
        description="Timestamp of the sample log entry, format YYYY-MM-DD HH:MM:SS.",
    )
    machine: str | None = Field(
        default=None,
        description="Machine or server named in the log, when the log includes one.",
    )
    citations: List[IssueCitation] | None = Field(
        default=None,
        description="File path and line number copied from tool output. Do not invent locations.",
    )


class IssuesReported(BaseModel):
    issues: List[IssueReport] = Field(
        description="Issues found in the logs, most severe first. Empty when the window has no problems."
    )
