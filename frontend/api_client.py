"""Stream one analysis turn from the Flask backend."""

from __future__ import annotations

import json

import requests
import streamlit as st

from config import BACKEND_URL


def _stream_backend_tokens(*, endpoint: str, payload: dict):
    """Yield text chunks from the Flask SSE response."""
    url = f"{BACKEND_URL.rstrip('/')}{endpoint}"
    with requests.post(url, json=payload, stream=True, timeout=600) as response:
        response.raise_for_status()
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data = json.loads(line[5:].strip())
            event_type = data.get("type")
            if event_type == "token" and data.get("text"):
                yield data["text"]
            elif event_type == "error":
                raise RuntimeError(data.get("message") or "Backend analysis failed")
            elif event_type == "done":
                break


def stream_response(api_route: str, payload: dict) -> str:
    try:
        response_text = st.write_stream(
            _stream_backend_tokens(endpoint=api_route, payload=payload)
        )
    except Exception as exc:
        response_text = (
            "The analysis failed while talking to the agent backend. "
            "This looks like a backend issue rather than a frontend one:\n\n"
            f"`{exc}`"
        )
        st.error(response_text)
    else:
        if not response_text:
            response_text = (
                "The agent finished but streamed no text back. This likely points "
                "to a backend issue rather than a frontend one."
            )
            st.warning(response_text)
    return response_text
