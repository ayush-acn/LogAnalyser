from pydantic import BaseModel, Field, field_validator, model_validator

from config import QUERY_SOURCE_NEW, QUERY_SOURCE_SCHEDULED, QUERY_SOURCES
from tools.access import resolve_allowed_file


class AnalysisRequest(BaseModel):
    log_file_path: str = Field(description="Absolute path to one log file inside an allowed log folder.")
    thread_id: str | None = Field(
        default=None,
        description="Optional thread id. Generated when omitted. A scheduled thread accepts one run.",
    )
    response_type: str = Field(
        default="TEXT",
        description="TEXT writes prose. JSON writes the structured answer.",
    )

    @field_validator("log_file_path")
    @classmethod
    def path_is_allowed(cls, value: str) -> str:
        return str(resolve_allowed_file(value))

    @field_validator("response_type")
    @classmethod
    def response_type_known(cls, value: str) -> str:
        return "JSON" if str(value).strip().upper() == "JSON" else "TEXT"


class QueryAnalysisRequest(AnalysisRequest):
    user_query: str = Field(description="User question about the logs or a scheduled report.")
    query_source: str = Field(
        default=QUERY_SOURCE_NEW,
        description="QUERY_SOURCE_NEW starts from the log file. QUERY_SOURCE_SCHEDULED starts from a scheduled report.",
    )
    scheduled_thread_id: str | None = Field(
        default=None,
        description="Scheduled thread id, including its run time, when query_source is QUERY_SOURCE_SCHEDULED.",
    )

    @field_validator("query_source")
    @classmethod
    def source_is_known(cls, value: str) -> str:
        if value not in QUERY_SOURCES:
            raise ValueError(f"query_source must be one of {QUERY_SOURCES}")
        return value

    @model_validator(mode="after")
    def scheduled_source_has_thread(self):
        if self.query_source == QUERY_SOURCE_SCHEDULED and not self.scheduled_thread_id:
            raise ValueError("scheduled_thread_id is required when query_source is scheduled")
        if self.query_source == QUERY_SOURCE_NEW:
            self.scheduled_thread_id = None
        return self


class HealthResponse(BaseModel):
    status: str = "ok"
