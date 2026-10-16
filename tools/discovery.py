"""Find log files and the rotated copies that belong together."""

from __future__ import annotations

import re
from pathlib import Path

from tools.settings import default_max_discover

DEFAULT_LOG_EXTENSIONS = {".log", ".txt", ".syslog", ".fscproxylog"}

# solr.log.1  (a bigger number is an older file)
_NUMERIC_ROTATION = re.compile(r"^(?P<stem>.+)\.log\.(?P<n>\d+)$", re.IGNORECASE)
# app_2026-07-30.log or app_2026-07-30_07_06_34.log
_DATED_SUFFIX = re.compile(
    r"^(?P<stem>.+)_(?P<date>\d{4}-\d{2}-\d{2})(?:_\d{2}_\d{2}_\d{2})?\.log$",
    re.IGNORECASE,
)
# ServerManager-2026-07-30-1.log
_SERVERMANAGER_DATED = re.compile(
    r"^ServerManager-(?P<date>\d{4}-\d{2}-\d{2})-(?P<n>\d+)\.log$",
    re.IGNORECASE,
)
# Teamcenter_Vault_Service.2026-07-30.log
_VAULT_DATED = re.compile(
    r"^(?P<stem>Teamcenter_Vault_Service|teamcenter_vault_service-(?:stdout|stderr))"
    r"\.(?P<date>\d{4}-\d{2}-\d{2})\.log$",
    re.IGNORECASE,
)
# name<8 hex chars>.syslog and the matching .fscproxylog
_HASH_PAIR = re.compile(
    r"^(?P<stem>.+)(?P<hash>[0-9a-f]{8})\.(?P<ext>syslog|fscproxylog)$",
    re.IGNORECASE,
)


def _creation_time(path: Path) -> float:
    stat = path.stat()
    return getattr(stat, "st_birthtime", stat.st_ctime)


def _is_log_name(path: Path, extensions: set[str]) -> bool:
    return path.suffix.lower() in extensions or _NUMERIC_ROTATION.match(path.name) is not None


def discover_logs(
    root_dir: str | Path,
    *,
    extensions: set[str] | None = None,
    max_files: int | None = None,
    skip_empty: bool = True,
) -> list[Path]:
    """List log files under a folder, newest first."""
    root = Path(root_dir)
    if not root.exists() or not root.is_dir():
        return []

    extensions = {
        ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        for ext in (extensions or DEFAULT_LOG_EXTENSIONS)
    }
    limit = default_max_discover() if max_files is None else max(1, int(max_files))

    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or not _is_log_name(path, extensions):
            continue
        if skip_empty:
            try:
                if path.stat().st_size == 0:
                    continue
            except OSError:
                continue
        files.append(path)

    files.sort(key=_creation_time, reverse=True)
    return files[:limit]


def _stem_from_log_name(name: str) -> str:
    match = _NUMERIC_ROTATION.match(name)
    if match:
        return match.group("stem")
    if name.lower().endswith(".log"):
        return name[:-4]
    return Path(name).stem


def _siblings(path: Path) -> list[Path]:
    return [item for item in path.parent.iterdir() if item.is_file()]


def _numeric_group(path: Path, siblings: list[Path]) -> list[Path] | None:
    name = path.name
    if not (_NUMERIC_ROTATION.match(name) or name.lower().endswith(".log")):
        return None

    stem = _stem_from_log_name(name)
    numbered: list[tuple[int, Path]] = []
    for sibling in siblings:
        match = _NUMERIC_ROTATION.match(sibling.name)
        if match and match.group("stem").lower() == stem.lower():
            numbered.append((int(match.group("n")), sibling))
    if not numbered:
        return None

    numbered.sort(key=lambda item: item[0], reverse=True)
    ordered = [item[1] for item in numbered]
    current = path.parent / f"{stem}.log"
    if current.exists() and current not in ordered:
        ordered.append(current)
    return ordered


def _dated_group(path: Path, siblings: list[Path]) -> list[Path] | None:
    match = _DATED_SUFFIX.match(path.name)
    stem = match.group("stem") if match else (path.stem if path.name.lower().endswith(".log") else None)
    if not stem:
        return None

    dated: list[tuple[str, Path]] = []
    for sibling in siblings:
        sibling_match = _DATED_SUFFIX.match(sibling.name)
        if sibling_match and sibling_match.group("stem").lower() == stem.lower():
            dated.append((sibling_match.group("date"), sibling))
    if not dated:
        return None

    dated.sort(key=lambda item: item[0])
    ordered = [item[1] for item in dated]
    current = path.parent / f"{stem}.log"
    if current.exists() and current not in ordered:
        ordered.append(current)
    return ordered


def _servermanager_group(path: Path, siblings: list[Path]) -> list[Path] | None:
    name = path.name
    if not (_SERVERMANAGER_DATED.match(name) or name.lower() == "servermanager.log"):
        return None

    dated: list[tuple[str, int, Path]] = []
    for sibling in siblings:
        match = _SERVERMANAGER_DATED.match(sibling.name)
        if match:
            dated.append((match.group("date"), int(match.group("n")), sibling))

    dated.sort(key=lambda item: (item[0], item[1]))
    ordered = [item[2] for item in dated]
    current = path.parent / "ServerManager.log"
    if current.exists() and current not in ordered:
        ordered.append(current)
    return ordered or None


def _vault_group(path: Path, siblings: list[Path]) -> list[Path] | None:
    match = _VAULT_DATED.match(path.name)
    if not match:
        return None

    stem = match.group("stem")
    dated: list[tuple[str, Path]] = []
    for sibling in siblings:
        sibling_match = _VAULT_DATED.match(sibling.name)
        if sibling_match and sibling_match.group("stem").lower() == stem.lower():
            dated.append((sibling_match.group("date"), sibling))
    if not dated:
        return None

    dated.sort(key=lambda item: item[0])
    return [item[1] for item in dated]


def _hash_pair_group(path: Path, _siblings: list[Path]) -> list[Path] | None:
    match = _HASH_PAIR.match(path.name)
    if not match:
        return None

    stem = match.group("stem")
    hash_id = match.group("hash")
    group: list[Path] = []
    for ext in ("syslog", "fscproxylog"):
        candidate = path.parent / f"{stem}{hash_id}.{ext}"
        if candidate.exists():
            group.append(candidate)
    return group or None


def resolve_log_group(file_path: str | Path) -> list[Path]:
    """Return every file in this log's rotation group, oldest first."""
    path = Path(file_path)
    if not path.exists():
        return []

    siblings = _siblings(path)
    for finder in (
        _numeric_group,
        _dated_group,
        _servermanager_group,
        _vault_group,
        _hash_pair_group,
    ):
        group = finder(path, siblings)
        if group:
            return group
    return [path]
