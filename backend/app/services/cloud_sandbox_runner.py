"""Optional cloud-sandbox runners (phase 24, 24-04).

``select_runner(risk, config)`` picks the execution target for the highest-risk
fully-autonomous runs (competitive-intel auto-implement, life-harness autonomy):

  * default → :class:`LocalRunner` (the Plan-01 OS sandbox at the local chokepoint);
  * :class:`E2BRunner` when ``E2B_API_KEY`` is present AND the run is highest-risk;
  * :class:`ModalRunner` when ``MODAL_TOKEN_ID``+``MODAL_TOKEN_SECRET`` are present
    AND the run is highest-risk.

Absent credentials degrade GRACEFULLY to local (logged skip). The e2b/modal SDKs
are imported LAZILY inside the adapter methods, so a missing optional dependency
NEVER raises ``ImportError`` at module import or during ``select_runner`` — the
whole point is that a cloud-less install keeps working (crit 3). The SDKs are
pinned as OPTIONAL extras (``pip install '.[cloud-sandbox]'``), not runtime deps.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Risk levels that are eligible for an offboard cloud sandbox.
_HIGH_RISK = {"high", "highest", "critical"}


def _has_e2b_creds() -> bool:
    return bool(os.environ.get("E2B_API_KEY"))


def _has_modal_creds() -> bool:
    return bool(os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET"))


class LocalRunner:
    """Default target: run locally behind the Plan-01 OS sandbox prefix.

    Thin by design — the ACTUAL launch stays in execution_service / goal_loop;
    this just names the local path and exposes the sandbox-prefix builder so a
    caller can wrap a command uniformly.
    """

    kind = "local"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def wrap(self, cmd, workspace, *, net: bool = True, proxy_url: str | None = None):
        from .sandbox_wrap import build_sandbox_prefix

        return build_sandbox_prefix(cmd, workspace, net=net, proxy_url=proxy_url)


class E2BRunner:
    """E2B cloud sandbox. SDK imported lazily; auth via ``E2B_API_KEY``."""

    kind = "e2b"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def run(self, cmd, *, timeout: int = 300):  # pragma: no cover - needs live creds (L3)
        from e2b import Sandbox  # lazy: never imported unless a cloud run is chosen

        sbx = Sandbox.create(timeout=timeout)
        try:
            return sbx.commands.run(" ".join(cmd))
        finally:
            sbx.kill()


class ModalRunner:
    """Modal cloud sandbox. SDK imported lazily; auth via ``MODAL_TOKEN_*``."""

    kind = "modal"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def run(self, cmd, *, timeout: int = 300):  # pragma: no cover - needs live creds (L3)
        import modal  # lazy: never imported unless a cloud run is chosen

        app = modal.App.lookup("agented-sandbox", create_if_missing=True)
        sb = modal.Sandbox.create(app=app)
        try:
            proc = sb.exec("bash", "-lc", " ".join(cmd), timeout=timeout)
            return proc
        finally:
            sb.terminate()


def select_runner(*, risk: str, config: dict | None = None):
    """Return the execution runner for a run of the given ``risk``.

    Highest-risk + credentialed → cloud (E2B preferred, then Modal); otherwise
    (or on absent credentials) :class:`LocalRunner`, with a logged graceful skip
    when a high-risk run wanted cloud but had no credentials. Non-high-risk runs
    ALWAYS get local regardless of credentials.
    """
    config = config or {}
    high = (risk or "").strip().lower() in _HIGH_RISK
    if high and _has_e2b_creds():
        return E2BRunner(config)
    if high and _has_modal_creds():
        return ModalRunner(config)
    if high:
        logger.info(
            "cloud sandbox: no E2B/Modal credentials present — falling back to "
            "LocalRunner (graceful skip; set E2B_API_KEY or MODAL_TOKEN_* to enable)."
        )
    return LocalRunner(config)
