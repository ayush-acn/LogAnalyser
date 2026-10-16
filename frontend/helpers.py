"""UI pieces used by the scheduled page and the query page."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from config import MODE_QUERY, MODE_SCHEDULED, QUERY_SOURCE_NEW, QUERY_SOURCE_SCHEDULED, thread_timestamp
from frontend.api_client import stream_response
from frontend.session import completed_scheduled_threads, create_thread, start_new_chat
from frontend.utils import discover_log_files, thread_label

QUERY_SOURCE_LABELS = {
    QUERY_SOURCE_NEW: "New chat",
    QUERY_SOURCE_SCHEDULED: "Scheduled report",
}


def render_sidebar(mode: str) -> None:
    if mode == MODE_SCHEDULED:
        new_label = "+ New analysis"
        history_caption = "Previous analyses"
        empty_caption = "No analyses yet."
    else:
        new_label = "+ New chat"
        history_caption = "Previous chats"
        empty_caption = "No chats yet."

    with st.sidebar:
        if st.button(new_label, use_container_width=True, key=f"new_chat_{mode}"):
            start_new_chat(mode)

        st.divider()
        st.caption(history_caption)

        thread_ids = [
            thread_id
            for thread_id in st.session_state.thread_order
            if st.session_state.threads[thread_id]["mode"] == mode
        ]
        if not thread_ids:
            st.caption(empty_caption)
            return

        active_id = st.session_state.active_thread.get(mode)
        for thread_id in thread_ids:
            thread = st.session_state.threads[thread_id]
            label = thread["label"] or thread_label(thread["mode"], None, thread_id)
            if st.button(
                label,
                key=f"thread_btn_{thread_id}",
                use_container_width=True,
                type="primary" if thread_id == active_id else "secondary",
            ):
                st.session_state.active_thread[mode] = thread_id


def _response_type() -> str:
    value = str(st.session_state.get("response_type", "TEXT")).strip().upper()
    return "JSON" if value == "JSON" else "TEXT"


def run_turn(thread_id: str, user_query: str | None, api_route: str) -> None:
    thread = st.session_state.threads[thread_id]
    messages = thread["messages"]
    had_history_before = len(messages) > 0

    if thread["label"] is None:
        thread["label"] = _label_for(thread, user_query, thread_id)

    if thread["mode"] == MODE_SCHEDULED:
        payload = {
            "log_file_path": thread["log_file"],
            "thread_id": thread_id,
            "response_type": _response_type(),
        }
        response_text = stream_response(api_route, payload)
        messages.append(AIMessage(content=response_text))
        return

    if user_query:
        st.chat_message("user").write(user_query)

    payload = {
        "log_file_path": thread["log_file"],
        "thread_id": thread_id,
        "user_query": user_query or "",
        "query_source": thread.get("query_source", QUERY_SOURCE_NEW),
        "scheduled_thread_id": thread.get("scheduled_thread_id"),
        "response_type": _response_type(),
    }

    with st.chat_message("assistant"):
        response_text = stream_response(api_route, payload)

    if not had_history_before and not any(isinstance(message, HumanMessage) for message in messages):
        messages.append(HumanMessage(content=user_query or "Analyse the log file and report the problems."))
    elif user_query and had_history_before:
        messages.append(HumanMessage(content=user_query))

    messages.append(AIMessage(content=response_text))


def render_message_history(messages) -> None:
    for message in messages:
        if isinstance(message, HumanMessage):
            st.chat_message("user").write(message.content)
        elif isinstance(message, AIMessage):
            st.chat_message("assistant").write(message.content)


def render_start_form(mode: str, *, api_route: str, require_query: bool) -> None:
    nonce = st.session_state.draft_nonce[mode]
    if require_query:
        _render_query_start(nonce, api_route)
        return
    _render_scheduled_start(nonce, api_route)


def render_scheduled_report(thread_id: str) -> None:
    thread = st.session_state.threads[thread_id]
    st.subheader("Analysis report")
    st.caption(f"Run: `{thread_timestamp(thread_id) or thread_id}`")
    st.caption(f"Log file: `{thread['log_file']}`")
    reports = [message for message in thread["messages"] if isinstance(message, AIMessage)]
    if not reports:
        st.caption("No report was produced for this analysis.")
        return
    for message in reports:
        st.write(message.content)


def render_active_chat(thread_id: str, api_route: str) -> None:
    thread = st.session_state.threads[thread_id]
    st.subheader("Chat")
    if thread.get("query_source") == QUERY_SOURCE_SCHEDULED and thread.get("scheduled_thread_id"):
        when = thread_timestamp(thread["scheduled_thread_id"]) or thread["scheduled_thread_id"]
        st.caption(f"Scheduled report: `{when}`")
    st.caption(f"Log file: `{thread['log_file']}`")
    render_message_history(thread["messages"])

    follow_up = st.chat_input("Ask a follow-up question...")
    if follow_up:
        run_turn(thread_id, follow_up, api_route)
        st.rerun()


def _label_for(thread: dict, user_query: str | None, thread_id: str) -> str:
    if thread.get("query_source") == QUERY_SOURCE_SCHEDULED and thread.get("scheduled_thread_id"):
        when = thread_timestamp(thread["scheduled_thread_id"]) or thread["scheduled_thread_id"]
        question = (user_query or "Query").strip()
        question = question[:32] + ("..." if len(question) > 32 else "")
        return f"{question}  on {when}"
    return thread_label(thread["mode"], user_query, thread_id)


def _render_scheduled_start(nonce: int, api_route: str) -> None:
    st.caption("One file, one report. Follow-up questions are on the Query page.")
    selected = _select_log_file(MODE_SCHEDULED, nonce)
    if selected is None:
        return
    if st.button("Start analysis", type="primary"):
        thread_id = create_thread(MODE_SCHEDULED, selected)
        run_turn(thread_id, None, api_route)
        st.rerun()


def _render_query_start(nonce: int, api_route: str) -> None:
    source = st.radio(
        "Start from",
        options=[QUERY_SOURCE_NEW, QUERY_SOURCE_SCHEDULED],
        format_func=lambda value: QUERY_SOURCE_LABELS[value],
        horizontal=True,
        key=f"draft_source_{nonce}",
    )
    if source == QUERY_SOURCE_SCHEDULED:
        _render_scheduled_query_start(nonce, api_route)
        return

    selected = _select_log_file(MODE_QUERY, nonce)
    if selected is None:
        return
    user_query = st.text_input(
        "Your question",
        key=f"draft_query_{MODE_QUERY}_{nonce}",
    )
    ready = bool(user_query.strip())
    if not ready:
        st.caption("Enter a question to enable the button.")
    if st.button("Start chat", type="primary", disabled=not ready):
        thread_id = create_thread(MODE_QUERY, selected, query_source=QUERY_SOURCE_NEW)
        run_turn(thread_id, user_query.strip(), api_route)
        st.rerun()


def _render_scheduled_query_start(nonce: int, api_route: str) -> None:
    reports = completed_scheduled_threads()
    if not reports:
        st.info("Run a scheduled analysis first. Its report can be used as the starting context.")
        return

    options = [thread_id for thread_id, _thread in reports]
    selected_thread = st.selectbox(
        "Scheduled report",
        options=options,
        format_func=lambda thread_id: _scheduled_option_label(thread_id),
        key=f"draft_scheduled_{nonce}",
    )
    if not selected_thread:
        return
    user_query = st.text_input(
        "Your question",
        key=f"draft_query_{QUERY_SOURCE_SCHEDULED}_{nonce}",
    )
    ready = bool(user_query.strip())
    if not ready:
        st.caption("Enter a question to enable the button.")
    if st.button("Ask about this report", type="primary", disabled=not ready):
        source_thread = st.session_state.threads[selected_thread]
        thread_id = create_thread(
            MODE_QUERY,
            source_thread["log_file"],
            query_source=QUERY_SOURCE_SCHEDULED,
            scheduled_thread_id=selected_thread,
        )
        run_turn(thread_id, user_query.strip(), api_route)
        st.rerun()


def _scheduled_option_label(thread_id: str) -> str:
    thread = st.session_state.threads[thread_id]
    when = thread_timestamp(thread_id) or thread_id
    name = Path(thread["log_file"]).name
    return f"{when}  {name}"


def _select_log_file(mode: str, nonce: int) -> str | None:
    folder_raw = st.text_input(
        "Absolute path to log folder",
        placeholder=r"C:\path\to\logs",
        key=f"draft_folder_{mode}_{nonce}",
    )
    folder_path = Path(folder_raw.strip()) if folder_raw.strip() else None
    if not folder_path:
        st.caption("Enter an absolute folder path to list log files.")
        return None
    if not folder_path.exists():
        st.error(f"Path does not exist: `{folder_path}`")
        return None
    if not folder_path.is_dir():
        st.error(f"Path is not a folder: `{folder_path}`")
        return None

    try:
        log_files = discover_log_files(folder_path)
    except ValueError as exc:
        st.error(str(exc))
        return None
    if not log_files:
        st.error(f"No log files found under `{folder_path}`.")
        return None

    folder_resolved = folder_path.resolve()
    options = [str(path.resolve()) for path in log_files]
    selected = st.selectbox(
        "Log file to analyse",
        options=options,
        format_func=lambda value: str(Path(value).relative_to(folder_resolved)),
        key=f"draft_file_{mode}_{nonce}",
    )
    return str(Path(selected).resolve()) if selected else None
