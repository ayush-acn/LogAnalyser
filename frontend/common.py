"""Shared chat UI used by the scheduled-analysis and query pages."""

from __future__ import annotations

import json
from pathlib import Path

import requests
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from config import BACKEND_URL
from frontend_utils import ALL_FILES_OPTION, discover_log_files, generate_thread_id, thread_label


def init_session_state() -> None:
    st.session_state.setdefault("threads", {})
    st.session_state.setdefault("thread_order", [])
    st.session_state.setdefault("active_thread", {"query": None, "scheduled": None})
    st.session_state.setdefault("draft_nonce", {"query": 0, "scheduled": 0})


def _start_new_chat(mode: str) -> None:
    st.session_state.active_thread[mode] = None
    st.session_state.draft_nonce[mode] += 1


def _active_thread(mode: str):
    thread_id = st.session_state.active_thread.get(mode)
    thread = st.session_state.threads.get(thread_id) if thread_id else None
    if not thread or thread["mode"] != mode:
        return None, None
    return thread_id, thread


def _create_thread(mode: str, log_target: str) -> str:
    thread_id = generate_thread_id(mode)
    st.session_state.threads[thread_id] = {
        "mode": mode,
        "log_file": log_target,
        "messages": [],
        "label": None,
    }
    st.session_state.thread_order.insert(0, thread_id)
    st.session_state.active_thread[mode] = thread_id
    return thread_id


def _resolve_log_selection(selection: str, log_files: list[Path]) -> str:
    if selection == ALL_FILES_OPTION:
        return "\n".join(str(path.resolve()) for path in log_files)
    return str(Path(selection).resolve())


def _render_sidebar(mode: str) -> None:
    with st.sidebar:
        if st.button("+ New chat", use_container_width=True, key=f"new_chat_{mode}"):
            _start_new_chat(mode)

        st.divider()
        st.caption("Previous chats")

        thread_ids = [
            thread_id
            for thread_id in st.session_state.thread_order
            if st.session_state.threads[thread_id]["mode"] == mode
        ]
        if not thread_ids:
            st.caption("No chats yet.")
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


def _run_turn(thread_id: str, user_query: str | None, api_route: str) -> None:
    thread = st.session_state.threads[thread_id]
    messages = thread["messages"]
    had_history_before = len(messages) > 0

    if thread["label"] is None:
        thread["label"] = thread_label(thread["mode"], user_query, thread_id)

    if user_query:
        st.chat_message("user").write(user_query)

    payload = {
        "log_file_path": thread["log_file"],
        "thread_id": thread_id,
    }
    if user_query:
        payload["user_query"] = user_query
    elif thread["mode"] == "query":
        payload["user_query"] = ""

    with st.chat_message("assistant"):
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

    if not had_history_before and not any(isinstance(message, HumanMessage) for message in messages):
        messages.append(
            HumanMessage(content=user_query or "Please analyse the latest logs from the file.")
        )
    elif user_query and had_history_before:
        messages.append(HumanMessage(content=user_query))

    messages.append(AIMessage(content=response_text))


def _render_message_history(messages) -> None:
    for message in messages:
        if isinstance(message, HumanMessage):
            st.chat_message("user").write(message.content)
        elif isinstance(message, AIMessage):
            st.chat_message("assistant").write(message.content)


def _log_display(log_file: str) -> str:
    if "\n" in log_file:
        return f"All files ({len(log_file.splitlines())})"
    return log_file


def _render_start_form(mode: str, *, api_route: str, require_query: bool) -> None:
    nonce = st.session_state.draft_nonce[mode]
    user_query = None
    if require_query:
        user_query = st.text_input(
            "Your question about the logs",
            key=f"draft_query_{mode}_{nonce}",
        )
    else:
        st.caption("No question needed. The agent analyses the latest logs on its own.")

    folder_raw = st.text_input(
        "Absolute path to log folder",
        placeholder=r"C:\path\to\logs",
        key=f"draft_folder_{mode}_{nonce}",
    )
    folder_path = Path(folder_raw.strip()) if folder_raw.strip() else None
    if not folder_path:
        st.caption("Enter an absolute folder path to list log files.")
        return
    if not folder_path.exists():
        st.error(f"Path does not exist: `{folder_path}`")
        return
    if not folder_path.is_dir():
        st.error(f"Path is not a folder: `{folder_path}`")
        return

    log_files = discover_log_files(folder_path)
    if not log_files:
        st.error(f"No log files found under `{folder_path}`.")
        return

    options = [ALL_FILES_OPTION, *[str(path.resolve()) for path in log_files]]
    selected = st.selectbox(
        "Log file to analyse",
        options=options,
        format_func=lambda value: (
            f"All files ({len(log_files)})"
            if value == ALL_FILES_OPTION
            else str(Path(value).relative_to(folder_path.resolve()))
        ),
        key=f"draft_file_{mode}_{nonce}",
    )

    ready = selected is not None and (not require_query or bool((user_query or "").strip()))
    if require_query and not ready:
        st.caption("Enter a question to enable the button.")

    if st.button("Start analysis", type="primary", disabled=not ready):
        log_target = _resolve_log_selection(selected, log_files)
        thread_id = _create_thread(mode, log_target)
        _run_turn(thread_id, user_query.strip() if user_query else None, api_route)
        st.rerun()


def _render_active_chat(thread_id: str, api_route: str) -> None:
    thread = st.session_state.threads[thread_id]
    st.subheader("Chat")
    st.caption(f"Log file: `{_log_display(thread['log_file'])}`")
    _render_message_history(thread["messages"])

    follow_up = st.chat_input("Ask a follow-up question...")
    if follow_up:
        _run_turn(thread_id, follow_up, api_route)
        st.rerun()


def render_analysis_page(
    *,
    mode: str,
    api_route: str,
    heading: str,
    blurb: str,
    require_query: bool,
) -> None:
    init_session_state()
    _render_sidebar(mode)

    st.subheader(heading)
    st.caption(blurb)
    st.caption(f"Backend: `{BACKEND_URL}{api_route}`")

    thread_id, _thread = _active_thread(mode)
    if thread_id is None:
        _render_start_form(mode, api_route=api_route, require_query=require_query)
    else:
        _render_active_chat(thread_id, api_route)
