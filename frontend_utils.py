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


LOG_FILE_EXTENSIONS = {'.log', '.txt', '.syslog', '.fscproxylog' , '.pjl', '.tmp'}
ALL_FILES_OPTION = '__all_files__'


def _creation_time(path: Path) -> float:
    '''
    Best-effort file creation time. Uses birth time when available,
    otherwise falls back to ctime (creation time on Windows).
    '''
    stat = path.stat()
    return getattr(stat, 'st_birthtime', stat.st_ctime)


def discover_log_files(logs_root: Path) -> list[Path]:
    '''
    Recursively lists every log file under the given folder,
    newest creation time first.
    '''
    if not logs_root.exists() or not logs_root.is_dir():
        return []

    files = [
        path for path in logs_root.rglob('*')
        if path.is_file() and path.suffix.lower() in LOG_FILE_EXTENSIONS
    ]
    return sorted(files, key=_creation_time, reverse=True)


def thread_label(mode: str, text: str | None, thread_id: str) -> str:
    '''
    Builds a short, unique label for a thread, to be shown in the sidebar history.
    '''
    base = text.strip() if text else ('Scheduled analysis' if mode == 'Scheduled Analyses' else 'Query')
    base = base[:40] + ('...' if len(base) > 40 else '')
    return f"{base}  ({thread_id[-6:]})"
