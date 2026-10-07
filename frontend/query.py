"""Query page. File selection plus a question about the logs."""

from frontend.common import render_analysis_page
from frontend.routes import QUERY_ANALYSIS_API


def render_query_page() -> None:
    render_analysis_page(
        mode="query",
        api_route=QUERY_ANALYSIS_API,
        heading="Query",
        blurb="Choose a log file and ask a question. The agent answers from the logs.",
        require_query=True,
    )
