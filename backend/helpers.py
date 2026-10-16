"""Request parsing and Server-Sent Event helpers for the API."""

from __future__ import annotations

import json

from flask import Response, jsonify, request, stream_with_context
from pydantic import BaseModel, ValidationError

from config import new_thread_id

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def parse_body(model: type[BaseModel]):
    try:
        body = model.model_validate(request.get_json(force=True) or {})
    except ValidationError as exc:
        return None, (jsonify({"error": exc.errors()}), 400)
    return body, None


def ensure_thread_id(mode: str, thread_id: str | None) -> str:
    if thread_id:
        return thread_id
    return new_thread_id(mode)


def sse_line(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def event_stream(generator) -> Response:
    return Response(
        stream_with_context(generator),
        mimetype="text/event-stream",
        headers=SSE_HEADERS,
    )
