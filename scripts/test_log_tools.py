"""Exercise all log tools against files under logs/."""
from __future__ import annotations

import json
import sys
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Tools.log_discovery import discover_logs, group_all_logs, resolve_log_group
from Tools.log_resources import LogResources, detect_log_type
from Tools.log_tools import (
    fetch_latest_logs,
    fetch_paginated_logs,
    fetch_timed_logs,
    list_logs,
    resolve_log_group_tool,
)

LOGS_ROOT = ROOT / "logs"
SAMPLE_N = 5


def _status(ok: bool, detail: str = "") -> dict:
    return {"ok": ok, "detail": detail}


def test_file(path: Path) -> dict:
    """Run all log tools against one file; return structured result."""
    fp = str(path.resolve())
    result: dict = {
        "path": fp,
        "folder": path.parent.relative_to(LOGS_ROOT).as_posix(),
        "name": path.name,
        "size": path.stat().st_size,
        "handler": detect_log_type(path),
        "tools": {},
    }

    if result["size"] == 0:
        for tool in ("latest_logs", "page_logs", "timed_logs", "resolve_log_group"):
            result["tools"][tool] = _status(True, "skipped (empty file)")
        return result

    # resolve_log_group
    try:
        group = resolve_log_group_tool.invoke({"file_path": fp})
        result["tools"]["resolve_log_group"] = _status(
            True, f"{len(group)} file(s) in rotation group"
        )
        result["rotation_count"] = len(group)
    except Exception as exc:
        result["tools"]["resolve_log_group"] = _status(False, str(exc))

    # latest_logs
    try:
        entries = fetch_latest_logs.invoke({"file_path": fp, "n": SAMPLE_N})
        ok = isinstance(entries, list)
        detail = f"{len(entries)} entries"
        if entries:
            ts = entries[-1].get("timestamp")
            detail += f", last_ts={ts}"
        result["tools"]["latest_logs"] = _status(ok, detail)
        result["sample_entry"] = entries[-1] if entries else None
    except Exception as exc:
        result["tools"]["latest_logs"] = _status(False, str(exc))

    # page_logs (skip=2)
    try:
        entries = fetch_paginated_logs.invoke({"file_path": fp, "n": 3, "skip": 2})
        result["tools"]["page_logs"] = _status(
            True, f"{len(entries)} entries (skip=2, n=3)"
        )
    except Exception as exc:
        result["tools"]["page_logs"] = _status(False, str(exc))

    # timed_logs — use last entry timestamp if available
    try:
        entries = fetch_latest_logs.invoke({"file_path": fp, "n": 1})
        if entries and entries[0].get("timestamp"):
            ts = datetime.fromisoformat(entries[0]["timestamp"])
            start = ts - timedelta(hours=24)
            end = ts + timedelta(minutes=1)
            timed = fetch_timed_logs.invoke(
                {
                    "file_path": fp,
                    "start_time": start,
                    "end_time": end,
                    "n": SAMPLE_N,
                }
            )
            result["tools"]["timed_logs"] = _status(
                True, f"{len(timed)} entries in 24h window ending {ts.isoformat(sep=' ')}"
            )
        else:
            result["tools"]["timed_logs"] = _status(
                True, "skipped (no timestamp in latest entry)"
            )
    except Exception as exc:
        result["tools"]["timed_logs"] = _status(False, str(exc))

    return result


def main() -> int:
    print("=" * 72)
    print("LOG TOOLS TEST RUN")
    print(f"Root: {LOGS_ROOT}")
    print("=" * 72)

    # Tool: list_logs
    print("\n[1/2] Testing list_logs ...")
    try:
        listed = list_logs.invoke({"root_dir": str(LOGS_ROOT), "max_files": 500})
        print(f"  OK — discovered {len(listed)} files")
    except Exception as exc:
        print(f"  FAIL — {exc}")
        return 1

    # Pick one representative file per handler type (prefer non-empty, varied folders)
    discovered = discover_logs(LOGS_ROOT, max_files=500)
    by_handler: dict[str, list[Path]] = defaultdict(list)
    for p in discovered:
        h = detect_log_type(p)
        by_handler[h].append(p)

    # Also ensure syslog/fscproxylog extensions are represented
    for p in LOGS_ROOT.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".syslog", ".fscproxylog"} and p.stat().st_size > 0:
            h = detect_log_type(p)
            if p not in by_handler[h]:
                by_handler[h].append(p)

    print("\n[2/2] Testing per-handler representative files ...")
    all_results: list[dict] = []
    handler_summary: dict[str, dict] = {}

    for handler in sorted(by_handler.keys()):
        files = sorted(by_handler[handler], key=lambda p: p.stat().st_size, reverse=True)
        # Test up to 2 representatives per handler (largest files)
        reps = files[:2]
        handler_summary[handler] = {"total_files": len(files), "tested": [], "pass": 0, "fail": 0}

        print(f"\n--- Handler: {handler} ({len(files)} files) ---")
        for path in reps:
            r = test_file(path)
            all_results.append(r)
            handler_summary[handler]["tested"].append(path.name)
            failed = [t for t, v in r["tools"].items() if not v["ok"]]
            if failed:
                handler_summary[handler]["fail"] += 1
                status = "FAIL"
            else:
                handler_summary[handler]["pass"] += 1
                status = "PASS"
            print(f"  [{status}] {path.parent.name}/{path.name} ({r['size']} bytes)")
            for tool, info in r["tools"].items():
                mark = "ok" if info["ok"] else "FAIL"
                print(f"       {tool}: {mark} — {info['detail']}")

    # Rotation group smoke test
    print("\n--- Rotation groups (group_all_logs) ---")
    groups = group_all_logs(LOGS_ROOT, max_files=500)
    multi = [g for g in groups if g["count"] > 1]
    print(f"  {len(groups)} unique groups, {len(multi)} with multiple files")

    # Summary table
    print("\n" + "=" * 72)
    print("SUMMARY BY HANDLER TYPE")
    print("=" * 72)
    print(f"{'Handler':<20} {'Files':>6} {'Tested':>8} {'Pass':>6} {'Fail':>6}")
    print("-" * 52)
    total_pass = total_fail = 0
    for handler, s in sorted(handler_summary.items()):
        print(
            f"{handler:<20} {s['total_files']:>6} {len(s['tested']):>8} "
            f"{s['pass']:>6} {s['fail']:>6}"
        )
        total_pass += s["pass"]
        total_fail += s["fail"]
    print("-" * 52)
    print(f"{'TOTAL':<20} {'':>6} {total_pass + total_fail:>8} {total_pass:>6} {total_fail:>6}")

    out = ROOT / "Results" / "log_tools_test_results.json"
    out.parent.mkdir(exist_ok=True)
    payload = {
        "run_at": datetime.now().isoformat(sep=" "),
        "logs_root": str(LOGS_ROOT),
        "list_logs_count": len(listed),
        "rotation_groups": len(groups),
        "handler_summary": handler_summary,
        "results": all_results,
    }
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nDetailed JSON: {out}")

    return 1 if total_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
