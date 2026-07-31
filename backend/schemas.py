from pydantic import BaseModel, Field

from Models.log_agent import IssuesReported


class AnalysisRequest(BaseModel):
    log_file_path: str = Field(description="Absolute path to a log file, or newline-separated paths.")
    thread_id: str | None = Field(
        default=None,
        description="Optional thread id. Generated when omitted.",
    )
    user_query: str | None = Field(
        default=None,
        description="Optional follow-up question (scheduled default analysis when omitted).",
    )


class QueryAnalysisRequest(AnalysisRequest):
    user_query: str = Field(description="User question about the logs.")


class HealthResponse(BaseModel):
    status: str = "ok"


class ScheduledAnalysisResult(BaseModel):
    """Final structured payload for scheduled analysis (also sent on SSE done)."""
    thread_id: str
    issues: IssuesReported
