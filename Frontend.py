from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import streamlit as st

from Resources.log_resources import DEFAULT_LATEST_LOGS, LogResources

try:
    from logAgent import chain
except Exception as exc:  # pragma: no cover - shown directly in UI
    chain = None
    CHAIN_IMPORT_ERROR = str(exc)
else:
    CHAIN_IMPORT_ERROR = None


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_LOGS_ROOT = PROJECT_ROOT / "logs"


@lru_cache(maxsize=128)
def detect_log_type(log_file: Path) -> str:
    with open(log_file, "r", encoding="utf-8", errors="replace") as file:
        for _ in range(200):
            line = file.readline()
            if not line:
                break
            stripped = line.rstrip("\n")
            if LogResources.WEB_LOG.match(stripped):
                return "web"
            if LogResources.POOL_LOG.match(stripped):
                return "pool"
    return "unknown"


def discover_log_files(logs_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for log_file in sorted(logs_root.rglob("*")):
        if not log_file.is_file():
            continue
        if log_file.suffix.lower() not in {".log", ".txt"}:
            continue

        rel_path = log_file.relative_to(PROJECT_ROOT).as_posix()
        records.append(
            {
                "id": rel_path,
                "label": log_file.name,
                "path": log_file,
                "type": detect_log_type(log_file),
                "folder": log_file.parent.name.lower(),
            }
        )
    return records


def filtered_records(
    records: list[dict[str, Any]],
    selected_type: str,
    selected_folder: str,
) -> list[dict[str, Any]]:
    result = records
    if selected_type != "all":
        result = [row for row in result if row["type"] == selected_type]
    if selected_folder != "all":
        result = [row for row in result if row["folder"] == selected_folder]
    return result


def parse_time_input(raw: str, selected_log_type: str) -> datetime:
    value = raw.strip()
    if not value:
        raise ValueError("Empty datetime value")

    web_formats = ["%Y-%m-%d %H:%M:%S,%f"]
    pool_formats = ["%Y/%m/%d-%H:%M:%S,%f UTC", "%Y/%m/%d-%H:%M:%S,%f"]

    if selected_log_type == "web":
        formats = web_formats
    elif selected_log_type == "pool":
        formats = pool_formats
    else:
        formats = web_formats + pool_formats

    for dt_format in formats:
        try:
            return datetime.strptime(value, dt_format)
        except ValueError:
            continue

    raise ValueError("Unsupported datetime format")


def run() -> None:
    st.set_page_config(page_title="Log Analyzer Demo", page_icon=":mag:", layout="wide")
    st.title("Log Analyzer")
    st.caption("Demo UI: choose an exact log type and file, then run analysis.")

    source_mode = st.radio(
        "Log source",
        options=["Demo (local file selection)", "Prod (metadata source - coming soon)"],
        horizontal=True,
    )

    if source_mode != "Demo (local file selection)":
        st.info("Prod metadata-based log discovery will be plugged in here.")
        st.stop()

    logs_root = DEFAULT_LOGS_ROOT
    if not logs_root.exists():
        st.error(f"Logs folder not found: `{logs_root}`")
        st.stop()

    records = discover_log_files(logs_root)
    if not records:
        st.warning("No `.log` files found under the logs folder.")
        st.stop()

    all_types = sorted({row["type"] for row in records})

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        selected_type = st.selectbox("Exact log type", options=["all", *all_types], index=0)

    type_scoped_records = records if selected_type == "all" else [
        row for row in records if row["type"] == selected_type
    ]
    all_folders = sorted({row["folder"] for row in type_scoped_records})

    with col2:
        selected_folder = st.selectbox("Folder", options=["all", *all_folders], index=0)

    rows = filtered_records(records, selected_type, selected_folder)
    with col3:
        selected_record_id = st.selectbox(
            "Particular log file",
            options=[row["id"] for row in rows],
            format_func=lambda record_id: next(
                row["label"] for row in rows if row["id"] == record_id
            ),
            index=0 if rows else None,
            placeholder="No file matches the selected filters",
        )

    if not rows:
        st.warning("No files match the selected type/folder filters.")
        st.stop()

    selected_row = next(row for row in rows if row["id"] == selected_record_id)
    selected_path = selected_row["path"]

    st.markdown(
        f"- **Selected type:** `{selected_row['type']}`  \n"
        f"- **Selected folder:** `{selected_row['folder']}`  \n"
        f"- **Selected file:** `{selected_row['label']}`"
    )

    log_fetcher = LogResources(selected_path.parent)
    default_recent_count = log_fetcher.default_latest_count or DEFAULT_LATEST_LOGS

    st.subheader("Log Input Mode")
    input_mode = st.radio(
        "How to pass logs?",
        options=[
            "Recent n logs",
            "With start and end time",
            "Pagination (skip recent, fetch older)",
        ],
        horizontal=True,
    )

    fetch_kwargs: dict[str, Any] = {}
    if input_mode == "Recent n logs":
        recent_limit = st.number_input(
            f"Recent log count (default is {default_recent_count})",
            min_value=1,
            max_value=100000,
            value=int(default_recent_count),
            step=1,
        )
        fetch_kwargs["limit"] = int(recent_limit)

    elif input_mode == "With start and end time":
        if selected_row["type"] == "web":
            st.caption("Datetime format: `YYYY-MM-DD HH:MM:SS,mmm`")
        elif selected_row["type"] == "pool":
            st.caption("Datetime format: `YYYY/MM/DD-HH:MM:SS,mmm UTC`")
        else:
            st.caption(
                "Datetime formats: `YYYY-MM-DD HH:MM:SS,mmm` or `YYYY/MM/DD-HH:MM:SS,mmm UTC`"
            )

        start_time_raw = st.text_input("Start time")
        end_time_raw = st.text_input("End time")

    else:
        from_bottom = st.number_input(
            "Skip latest logs",
            min_value=0,
            max_value=1000000,
            value=0,
            step=1,
        )
        page_limit = st.number_input(
            f"Older log count to fetch (default is {default_recent_count})",
            min_value=1,
            max_value=100000,
            value=int(default_recent_count),
            step=1,
        )
        fetch_kwargs["from_bottom"] = int(from_bottom)
        fetch_kwargs["limit"] = int(page_limit)

    analyse_clicked = st.button("Analyze Log", type="primary")
    if not analyse_clicked:
        return

    if chain is None:
        st.error(f"Could not initialize analysis chain from `logAgent.py`: {CHAIN_IMPORT_ERROR}")
        st.stop()

    if input_mode == "With start and end time":
        if not start_time_raw.strip() or not end_time_raw.strip():
            st.error("Please provide both start time and end time.")
            st.stop()

        try:
            fetch_kwargs["start_time"] = parse_time_input(start_time_raw, selected_row["type"])
            fetch_kwargs["end_time"] = parse_time_input(end_time_raw, selected_row["type"])
        except ValueError:
            st.error("Invalid datetime format. Please use the format shown above.")
            st.stop()

    logs = log_fetcher.fetch_logs_from_file(selected_path.name, **fetch_kwargs)

    if not logs:
        st.warning("No log entries found in the selected file.")
        st.stop()

    st.info(f"Analyzing `{len(logs)}` log entries...")

    with st.spinner("Running log analysis..."):
        try:
            analysis_output = chain.invoke({"logs": logs})
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")
            st.stop()

    st.subheader("Analysis Output")
    st.markdown(analysis_output)

    with st.expander("Fetched log entries (debug view)"):
        st.json(logs)


if __name__ == "__main__":
    run()
