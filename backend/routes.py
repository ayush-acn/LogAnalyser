"""Backend routes for the two analysis flows.

Paths must match frontend/routes.py.
"""

from __future__ import annotations

from flask import Flask, Response, jsonify, request, stream_with_context
from pydantic import BaseModel, ValidationError

from backend.schemas import AnalysisRequest, QueryAnalysisRequest
from backend.services import iter_sse_events

QUERY_ANALYSIS_ROUTE = "/query-analysis"
SCHEDULED_ANALYSIS_ROUTE = "/scheduled-analysis"

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _parse(model: type[BaseModel]):
    try:
        body = model.model_validate(request.get_json(force=True) or {})
    except ValidationError as exc:
        return None, (jsonify({"error": exc.errors()}), 400)
    return body, None


def _stream(
    mode: str,
    log_file_path: str,
    user_query: str | None,
    thread_id: str | None,
) -> Response:
    generator = iter_sse_events(
        mode=mode,
        log_file_path=log_file_path,
        user_query=user_query,
        thread_id=thread_id,
    )
    return Response(
        stream_with_context(generator),
        mimetype="text/event-stream",
        headers=_SSE_HEADERS,
    )


def query_analysis():
    body, error = _parse(QueryAnalysisRequest)
    if error is not None:
        return error
    return _stream("query", body.log_file_path, body.user_query, body.thread_id)


def scheduled_analysis():
    body, error = _parse(AnalysisRequest)
    if error is not None:
        return error
    return _stream("scheduled", body.log_file_path, body.user_query, body.thread_id)


def register_routes(app: Flask) -> None:
    app.add_url_rule(
        QUERY_ANALYSIS_ROUTE,
        endpoint="query_analysis",
        view_func=query_analysis,
        methods=["POST"],
    )
    app.add_url_rule(
        SCHEDULED_ANALYSIS_ROUTE,
        endpoint="scheduled_analysis",
        view_func=scheduled_analysis,
        methods=["POST"],
    )
