from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from Tools import DEFAULT_MAX_DISCOVER

DEFAULT_LOG_EXTENSIONS = {".log", ".txt", ".syslog", ".fscproxylog"}
SKIP_EMPTY_EXTENSIONS = {".pjl", ".tmp"}

_NUMERIC_ROTATION = re.compile(r"^(?P<stem>.+)\.log\.(?P<n>\d+)$", re.IGNORECASE)
_DATED_SUFFIX = re.compile(
    r"^(?P<stem>.+)_(?P<date>\d{4}-\d{2}-\d{2})(?:_\d{2}_\d{2}_\d{2})?\.log$",
    re.IGNORECASE,
)
_SERVERMANAGER_DATED = re.compile(
    r"^ServerManager-(?P<date>\d{4}-\d{2}-\d{2})-(?P<n>\d+)\.log$",
    re.IGNORECASE,
)
_VAULT_DATED = re.compile(
    r"^(?P<stem>Teamcenter_Vault_Service|teamcenter_vault_service-(?:stdout|stderr))"
    r"\.(?P<date>\d{4}-\d{2}-\d{2})\.log$",
    re.IGNORECASE,
)
_HASH_PAIR = re.compile(
    r"^(?P<stem>.+)(?P<hash>[0-9a-f]{8})\.(?P<ext>syslog|fscproxylog)$",
    re.IGNORECASE,
)


def _creation_time(path: Path) -> float:
    stat = path.stat()
    return getattr(stat, "st_birthtime", stat.st_ctime)


def discover_logs(
    root_dir: str | Path,
    *,
    extensions: set[str] | None = None,
    max_files: int | None = None,
    skip_empty: bool = True,
) -> list[Path]:
    """
    Recursively list log-like files under root_dir, newest first.
    Caps at max_files (DEFAULT_MAX_DISCOVER) — configurable, not a tiny hard 20.
    """
    root = Path(root_dir)
    if not root.exists() or not root.is_dir():
        return []

    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in (extensions or DEFAULT_LOG_EXTENSIONS)}
    limit = DEFAULT_MAX_DISCOVER if max_files is None else max(1, int(max_files))

    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        is_numeric_rot = _NUMERIC_ROTATION.match(path.name) is not None
        if suffix not in exts and not is_numeric_rot:
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
    rot = _NUMERIC_ROTATION.match(name)
    if rot:
        return rot.group("stem")
    if name.lower().endswith(".log"):
        return name[:-4]
    return Path(name).stem


def resolve_log_group(file_path: str | Path) -> list[Path]:
    """
    Return ordered paths for a logical log stream (oldest → newest).
    Always includes the given file when it exists.
    """
    path = Path(file_path)
    if not path.exists():
        return []

    parent = path.parent
    name = path.name
    siblings = [p for p in parent.iterdir() if p.is_file()]

    # Numeric rotations: solr.log + solr.log.N (higher N = older)
    if _NUMERIC_ROTATION.match(name) or name.lower().endswith(".log"):
        stem = _stem_from_log_name(name)
        numbered: list[tuple[int, Path]] = []
        for sib in siblings:
            m = _NUMERIC_ROTATION.match(sib.name)
            if m and m.group("stem").lower() == stem.lower():
                numbered.append((int(m.group("n")), sib))
        if numbered:
            numbered.sort(key=lambda item: item[0], reverse=True)
            ordered = [p for _, p in numbered]
            base = parent / f"{stem}.log"
            if base.exists() and base not in ordered:
                ordered.append(base)
            return ordered

    # Dated Teamcenter current + daily: fcc_Teamcenter.log + *_YYYY-MM-DD.log
    dated = _DATED_SUFFIX.match(name)
    stem = dated.group("stem") if dated else (path.stem if name.lower().endswith(".log") else None)
    if stem:
        dated_files: list[tuple[str, Path]] = []
        for sib in siblings:
            m = _DATED_SUFFIX.match(sib.name)
            if m and m.group("stem").lower() == stem.lower():
                dated_files.append((m.group("date"), sib))
        current = parent / f"{stem}.log"
        if dated_files:
            dated_files.sort(key=lambda item: item[0])
            ordered = [p for _, p in dated_files]
            if current.exists() and current not in ordered:
                ordered.append(current)
            return ordered

    # ServerManager.log + ServerManager-YYYY-MM-DD-N.log
    if _SERVERMANAGER_DATED.match(name) or name.lower() == "servermanager.log":
        dated_sm: list[tuple[str, int, Path]] = []
        for sib in siblings:
            m = _SERVERMANAGER_DATED.match(sib.name)
            if m:
                dated_sm.append((m.group("date"), int(m.group("n")), sib))
        if dated_sm or name.lower() == "servermanager.log":
            dated_sm.sort(key=lambda item: (item[0], item[1]))
            ordered = [p for _, _, p in dated_sm]
            current = parent / "ServerManager.log"
            if current.exists() and current not in ordered:
                ordered.append(current)
            if ordered:
                return ordered

    # Vault daily dated files
    vault = _VAULT_DATED.match(name)
    if vault:
        stem = vault.group("stem")
        dated_v: list[tuple[str, Path]] = []
        for sib in siblings:
            m = _VAULT_DATED.match(sib.name)
            if m and m.group("stem").lower() == stem.lower():
                dated_v.append((m.group("date"), sib))
        dated_v.sort(key=lambda item: item[0])
        if dated_v:
            return [p for _, p in dated_v]

    # syslog / fscproxylog hash pair
    pair = _HASH_PAIR.match(name)
    if pair:
        stem, hash_id = pair.group("stem"), pair.group("hash")
        group = []
        for ext in ("syslog", "fscproxylog"):
            candidate = parent / f"{stem}{hash_id}.{ext}"
            if candidate.exists():
                group.append(candidate)
        if group:
            return group

    return [path]


def group_all_logs(root_dir: str | Path, **kwargs: Any) -> list[dict[str, Any]]:
    """Discover files and collapse into unique logical groups."""
    files = discover_logs(root_dir, **kwargs)
    seen: set[str] = set()
    groups: list[dict[str, Any]] = []
    for path in files:
        members = resolve_log_group(path)
        key = "|".join(str(p.resolve()) for p in members)
        if key in seen:
            continue
        seen.add(key)
        groups.append(
            {
                "primary": str(members[-1] if members else path),
                "paths": [str(p) for p in members],
                "count": len(members),
            }
        )
    return groups
