"""Streamlit session state for query chats and scheduled reports."""

from __future__ import annotations

import streamlit as st

from config import MODE_QUERY, MODE_SCHEDULED, QUERY_SOURCE_NEW
from frontend.utils import generate_thread_id


def init_session_state() -> None:
    st.session_state.setdefault("threads", {})
    st.session_state.setdefault("thread_order", [])
    st.session_state.setdefault("active_thread", {MODE_QUERY: None, MODE_SCHEDULED: None})
    st.session_state.setdefault("draft_nonce", {MODE_QUERY: 0, MODE_SCHEDULED: 0})


def start_new_chat(mode: str) -> None:
    st.session_state.active_thread[mode] = None
    st.session_state.draft_nonce[mode] += 1


def active_thread(mode: str):
    thread_id = st.session_state.active_thread.get(mode)
    thread = st.session_state.threads.get(thread_id) if thread_id else None
    if not thread or thread["mode"] != mode:
        return None, None
    return thread_id, thread


def completed_scheduled_threads() -> list[tuple[str, dict]]:
    """Scheduled runs that already have a report, newest first."""
    found = []
    for thread_id in st.session_state.thread_order:
        thread = st.session_state.threads[thread_id]
        if thread["mode"] == MODE_SCHEDULED and thread["messages"]:
            found.append((thread_id, thread))
    return found


def create_thread(
    mode: str,
    log_target: str,
    *,
    query_source: str = QUERY_SOURCE_NEW,
    scheduled_thread_id: str | None = None,
) -> str:
    thread_id = generate_thread_id(mode)
    st.session_state.threads[thread_id] = {
        "mode": mode,
        "log_file": log_target,
        "messages": [],
        "label": None,
        "query_source": query_source,
        "scheduled_thread_id": scheduled_thread_id,
    }
    st.session_state.thread_order.insert(0, thread_id)
    st.session_state.active_thread[mode] = thread_id
    return thread_id
