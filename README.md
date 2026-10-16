# Log Analyser

Log analyser for Teamcenter. It reads log files, groups repeated problems, and asks Claude on Amazon Bedrock for a short report and recommendations.

The UI is Streamlit. The API is Flask. The agent is a LangGraph flow.

## Layout

```
streamlit_app.py     Streamlit entrypoint
config.py            Modes, thread ids, model, server, and log-folder settings
agent/
  graph.py           Graph wiring
  nodes.py           Node functions
  helpers.py         Model clients, prompts selection, scheduled-report lookup
  runner.py          One analysis turn
tools/
  log_tools.py       The three tools the model can call
  helpers.py         Time parsing and rotation lookup for those tools
  parsers/           One parser per log format
backend/             Flask API
frontend/            Streamlit pages
docs/                Graph diagram, written when the app starts
logs/                Sample logs
```

## Setup

- Python 3.10 or newer
- AWS credentials that can call Bedrock in `us-east-1`

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` when you need to change a setting. `LOG_ROOTS` is a semicolon-separated list of folders the tools are allowed to read. When it is empty, only the repo `logs` folder is allowed.

## Run

Backend:

```bash
python -m backend.app
```

UI:

```bash
streamlit run streamlit_app.py
```

Starting the backend writes `docs/graph.png` (and `docs/graph.mmd` if the image service is unavailable). That save runs from `agent/graph.py`. Remove the `save_graph_diagram` call before a production deploy.

## Modes

Scheduled analysis is the default. Choose one log file. The agent calls `log_overview`, then `get_context` for the top problems, and returns one report. The thread id includes the run time, for example `scheduled_20261015T171400_ab12cd34`.

Query has two starts:

1. New chat. Choose a log file and ask a question. The model can call `log_overview`, `search_logs`, and `get_context`, with a cap on how many rounds it gets.
2. Scheduled report. Pick an existing scheduled run by its time and ask about that report. The backend loads that thread's report into the first message. The model uses the log tools only when the report does not already answer the question. The backend process that produced the report has to still be running, because the report is kept in memory on that thread id.

## Tools

`tools/log_tools.py` is the only file the model uses:

- `log_overview` summarises warnings and errors. Without a time range it reads the newest part of the file, up to a byte budget, including rotated copies.
- `search_logs` finds entries by text or level in that same window.
- `get_context` returns the raw lines around a cited line.

Every response is size-capped and says when the scan or the text was cut short.
