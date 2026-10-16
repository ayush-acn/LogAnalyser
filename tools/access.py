"""Allow-list for log paths. Tools and the API refuse anything outside these folders."""

from __future__ import annotations

from pathlib import Path

from config import log_roots


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def resolve_allowed_dir(folder: str | Path) -> Path:
    """Return a resolved directory that sits inside an allowed root."""
    path = Path(folder)
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"Path is not a folder: {path}")
    resolved = path.resolve()
    if not any(_within(resolved, root) for root in log_roots()):
        raise ValueError(f"Path is outside the allowed log folders: {resolved}")
    return resolved


def resolve_allowed_file(file_path: str | Path) -> Path:
    """Return a resolved file that sits inside an allowed root."""
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    resolved = path.resolve()
    if not any(_within(resolved, root) for root in log_roots()):
        raise ValueError(f"Path is outside the allowed log folders: {resolved}")
    return resolved
