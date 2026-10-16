from __future__ import annotations

import logging

from flask import Flask, jsonify
from flask_cors import CORS

from backend.routes import register_routes
from backend.schemas import HealthResponse
from config import BACKEND_HOST, BACKEND_PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    @app.get("/health")
    def health():
        return jsonify(HealthResponse().model_dump())

    register_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=BACKEND_HOST, port=BACKEND_PORT, debug=False, threaded=True)
