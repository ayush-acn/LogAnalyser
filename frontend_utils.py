from pathlib import Path
from uuid import uuid4

def generate_thread_id(generation_type: str):
    '''
    This function generates a thread id for the query or scheduled task.
    '''
    if generation_type == 'query':
        return 'query_'+str(uuid4())
    elif generation_type == 'scheduled':
        return 'scheduled_'+str(uuid4())
    else:
        raise ValueError(f"Invalid generation type: {generation_type}")


LOG_FILE_EXTENSIONS = {'.log', '.txt'}

def discover_log_files(logs_root: Path) -> list[Path]:
    '''
    Recursively lists every log file available under the logs root folder,
    so the user can pick one from the frontend.
    '''
    if not logs_root.exists():
        return []

    return sorted(
        path for path in logs_root.rglob('*')
        if path.is_file() and path.suffix.lower() in LOG_FILE_EXTENSIONS
    )


def thread_label(mode: str, text: str | None, thread_id: str) -> str:
    '''
    Builds a short, unique label for a thread, to be shown in the sidebar history.
    '''
    base = text.strip() if text else ('Scheduled analysis' if mode == 'Scheduled Analyses' else 'Query')
    base = base[:40] + ('...' if len(base) > 40 else '')
    return f"{base}  ({thread_id[-6:]})"