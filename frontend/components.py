"""Scheduled analysis page and query page."""

from __future__ import annotations

import streamlit as st

from config import BACKEND_URL, MODE_SCHEDULED
from frontend.helpers import render_active_chat, render_scheduled_report, render_sidebar, render_start_form
from frontend.session import active_thread, init_session_state


def render_analysis_page(
    *,
    mode: str,
    api_route: str,
    heading: str,
    blurb: str,
    require_query: bool,
) -> None:
    init_session_state()
    render_sidebar(mode)

    st.subheader(heading)
    st.caption(blurb)
    st.caption(f"Backend: `{BACKEND_URL}{api_route}`")

    thread_id, _thread = active_thread(mode)
    if thread_id is None:
        render_start_form(mode, api_route=api_route, require_query=require_query)
    elif mode == MODE_SCHEDULED:
        render_scheduled_report(thread_id)
    else:
        render_active_chat(thread_id, api_route)
