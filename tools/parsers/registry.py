from __future__ import annotations

from tools.parsers.base import FormatHandler
from tools.parsers.formats import (
    CommonsDaemonHandler,
    DeploymentCentreHandler,
    JulPairHandler,
    JvmGcHandler,
    PoolHandler,
    RacHandler,
    RawHandler,
    TcMldHandler,
    UtilityBannerHandler,
    VsBracketHandler,
    WebHandler,
)

# First match wins. Raw is last because it accepts any text.
_HANDLERS: list[FormatHandler] = [
    WebHandler(),
    PoolHandler(),
    JvmGcHandler(),
    CommonsDaemonHandler(),
    DeploymentCentreHandler(),
    RacHandler(),
    VsBracketHandler(),
    JulPairHandler(),
    TcMldHandler(),
    UtilityBannerHandler(),
    RawHandler(),
]

_BY_NAME = {handler.name: handler for handler in _HANDLERS}


def detect_handler(sample_lines: list[str], path_hint: str | None = None) -> FormatHandler:
    """Pick the format for this file. The filename is only a hint."""
    hint = (path_hint or "").lower()

    # Check the filename hint first. If that format does not fit, keep looking.
    if "solr_gc" in hint or hint.endswith("_gc.log") or "_gc.log." in hint:
        if _BY_NAME["jvm_gc"].detect(sample_lines):
            return _BY_NAME["jvm_gc"]
    if "vault_service" in hint or "commons daemon" in "\n".join(sample_lines).lower():
        if _BY_NAME["commons_daemon"].detect(sample_lines):
            return _BY_NAME["commons_daemon"]
    if "tcrac" in hint:
        if _BY_NAME["rac"].detect(sample_lines):
            return _BY_NAME["rac"]
    if "stderr" in hint:
        if _BY_NAME["jul_pair"].detect(sample_lines):
            return _BY_NAME["jul_pair"]

    for handler in _HANDLERS:
        if handler.detect(sample_lines):
            return handler
    return _BY_NAME["raw"]
