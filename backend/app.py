from __future__ import annotations

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS
from pydantic import ValidationError

from backend.schemas import HealthResponse, QueryAnalysisRequest, AnalysisRequest
from backend.services import iter_sse_events
from config import BACKEND_HOST, BACKEND_PORT


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    @app.get("/health")
    def health():
        return jsonify(HealthResponse().model_dump())

    @app.post("/query-analysis")
    def query_analysis():
        try:
            body = QueryAnalysisRequest.model_validate(request.get_json(force=True) or {})
        except ValidationError as exc:
            return jsonify({"error": exc.errors()}), 400

        generator = iter_sse_events(
            mode="query",
            log_file_path=body.log_file_path,
            user_query=body.user_query,
            thread_id=body.thread_id,
        )
        return Response(
            stream_with_context(generator),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/scheduled-analysis")
    def scheduled_analysis():
        try:
            body = AnalysisRequest.model_validate(request.get_json(force=True) or {})
        except ValidationError as exc:
            return jsonify({"error": exc.errors()}), 400

        # Stream tokens for UX parity; final SSE event carries IssuesReported JSON.
        generator = iter_sse_events(
            mode="scheduled",
            log_file_path=body.log_file_path,
            user_query=body.user_query,
            thread_id=body.thread_id,
        )
        return Response(
            stream_with_context(generator),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=BACKEND_HOST, port=BACKEND_PORT, debug=False, threaded=True)
