"""Backend routes for the two analysis flows.

Paths must match frontend/routes.py.
"""

from __future__ import annotations

from flask import Flask, jsonify

from agent import SCHEDULED_THREAD_CLOSED, scheduled_thread_is_new
from backend.helpers import event_stream, parse_body
from backend.schemas import AnalysisRequest, QueryAnalysisRequest
from backend.services import iter_sse_events
from config import MODE_QUERY, MODE_SCHEDULED

QUERY_ANALYSIS_ROUTE = "/query-analysis"
SCHEDULED_ANALYSIS_ROUTE = "/scheduled-analysis"


def query_analysis():
    body, error = parse_body(QueryAnalysisRequest)
    if error is not None:
        return error
    return event_stream(
        iter_sse_events(
            mode=MODE_QUERY,
            log_file_path=body.log_file_path,
            user_query=body.user_query,
            thread_id=body.thread_id,
            query_source=body.query_source,
            scheduled_thread_id=body.scheduled_thread_id,
            response_type=body.response_type,
        )
    )


def scheduled_analysis():
    body, error = parse_body(AnalysisRequest)
    if error is not None:
        return error
    if not scheduled_thread_is_new(body.thread_id):
        return jsonify({"error": SCHEDULED_THREAD_CLOSED}), 409
    return event_stream(
        iter_sse_events(
            mode=MODE_SCHEDULED,
            log_file_path=body.log_file_path,
            user_query=None,
            thread_id=body.thread_id,
            response_type=body.response_type,
        )
    )


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
