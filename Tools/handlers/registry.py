from __future__ import annotations

from Tools.handlers.base import FormatHandler
from Tools.handlers.web import WebHandler
from Tools.handlers.pool import PoolHandler
from Tools.handlers.tc_mld import TcMldHandler
from Tools.handlers.deploymentcentre import DeploymentCentreHandler
from Tools.handlers.jvm_gc import JvmGcHandler
from Tools.handlers.commons_daemon import CommonsDaemonHandler
from Tools.handlers.jul_pair import JulPairHandler
from Tools.handlers.rac import RacHandler
from Tools.handlers.vs_bracket import VsBracketHandler
from Tools.handlers.utility_banner import UtilityBannerHandler
from Tools.handlers.raw import RawHandler

# First match wins. Raw is always last.
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


def list_handlers() -> list[FormatHandler]:
    return list(_HANDLERS)


def get_handler(name: str) -> FormatHandler | None:
    return _BY_NAME.get(name)


def detect_handler(sample_lines: list[str], path_hint: str | None = None) -> FormatHandler:
    """Pick the first handler that claims the sample; raw always matches."""
    hint = (path_hint or "").lower()
    # Light path-based biases before generic TC MLD.
    if "solr_gc" in hint or hint.endswith("_gc.log") or "_gc.log." in hint:
        gc = _BY_NAME["jvm_gc"]
        if gc.detect(sample_lines):
            return gc
    if "vault_service" in hint or "commons daemon" in "\n".join(sample_lines).lower():
        daemon = _BY_NAME["commons_daemon"]
        if daemon.detect(sample_lines):
            return daemon
    if "tcrac" in hint:
        rac = _BY_NAME["rac"]
        if rac.detect(sample_lines):
            return rac
    if "stderr" in hint:
        jul = _BY_NAME["jul_pair"]
        if jul.detect(sample_lines):
            return jul

    for handler in _HANDLERS:
        if handler.detect(sample_lines):
            return handler
    return _BY_NAME["raw"]
