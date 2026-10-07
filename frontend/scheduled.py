"""Scheduled analysis page. File selection only — no user question."""

from frontend.common import render_analysis_page
from frontend.routes import SCHEDULED_ANALYSIS_API


def render_scheduled_page() -> None:
    render_analysis_page(
        mode="scheduled",
        api_route=SCHEDULED_ANALYSIS_API,
        heading="Scheduled analysis",
        blurb="Choose a log folder and file. The agent reviews the latest logs and reports issues.",
        require_query=False,
    )
