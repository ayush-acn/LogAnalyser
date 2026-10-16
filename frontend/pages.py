"""The two Streamlit pages: a scheduled report, and a question about logs or a report."""

from config import MODE_QUERY, MODE_SCHEDULED
from frontend.components import render_analysis_page
from frontend.routes import QUERY_ANALYSIS_API, SCHEDULED_ANALYSIS_API


def render_scheduled_page() -> None:
    render_analysis_page(
        mode=MODE_SCHEDULED,
        api_route=SCHEDULED_ANALYSIS_API,
        heading="Scheduled analysis",
        blurb="Default analysis. Choose one log file. The agent returns a single report.",
        require_query=False,
    )


def render_query_page() -> None:
    render_analysis_page(
        mode=MODE_QUERY,
        api_route=QUERY_ANALYSIS_API,
        heading="Query",
        blurb="Start a new chat on a log file, or ask about a scheduled report.",
        require_query=True,
    )
