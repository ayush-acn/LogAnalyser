"""Streamlit entrypoint.

Two page routes:
- /scheduled-analysis  -> scheduled analysis (no user question)
- /query               -> query (log file + question)

Streamlit serves one page at the app root. A hidden root page only redirects
to scheduled analysis so both routes keep their own URLs.
"""

import streamlit as st

from frontend.query import render_query_page
from frontend.routes import QUERY_PAGE, SCHEDULED_PAGE
from frontend.scheduled import render_scheduled_page

st.set_page_config(page_title="Log Analyser", page_icon=":mag:", layout="wide")

scheduled_page = st.Page(
    render_scheduled_page,
    title="Scheduled Analysis",
    url_path=SCHEDULED_PAGE,
)
query_page = st.Page(
    render_query_page,
    title="Query",
    url_path=QUERY_PAGE,
)


def _open_scheduled_analysis() -> None:
    st.switch_page(scheduled_page)


root_page = st.Page(
    _open_scheduled_analysis,
    title="Home",
    default=True,
    visibility="hidden",
)


def main() -> None:
    st.navigation([root_page, scheduled_page, query_page]).run()


if __name__ == "__main__":
    main()
