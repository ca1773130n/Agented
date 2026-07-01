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
import shlex
import uuid

logger = logging.getLogger(__name__)

# Risk levels that are eligible for an offboard cloud sandbox.
_HIGH_RISK = {"high", "highest", "critical"}


def _requires_goal_loop(session_config: dict) -> bool:
    """True iff ``session_config`` carries goal-loop / PSM semantics that a cmd-only
    cloud runner CANNOT honor.

    SECURITY (24-fix, BLOCKER 3): the E2B/Modal runners only run ``session_config["cmd"]``
    in an ephemeral sandbox and return a SYNTHETIC session id — they do not drive the
    governed goal-loop (human_gate, quality_gate, iteration records, a trackable PSM
    session). Routing goal-loop work to such a runner would silently degrade a
    governed loop into a fire-and-forget command while the caller believes a real
    goal-loop ran. This flag lets the cloud runners fall back to the local goal-loop
    for that work instead of executing the degraded stub. Never raises.
    """
    if not isinstance(session_config, dict):
        return False
    return bool(
        session_config.get("goal_loop_config")
        or session_config.get("execution_type") == "goal_loop"
        or session_config.get("requires_goal_loop")
    )


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

    def execute(self, session_config: dict):
        """Run the session locally via the ``goal_loop`` execution handler.

        This IS today's path — the caller (competitor auto-implement) used to call
        the handler inline while only *logging* the selected runner (24-fix, MAJOR
        11: dead routing). Routing execution through ``runner.execute`` makes the
        selected runner actually run the work; ``LocalRunner`` reproduces the prior
        goal-loop launch EXACTLY (worktree + human_gate + DB session), so there is
        no behaviour change when local is selected.
        """
        from .execution_type_handler import get_handler

        handler = get_handler("goal_loop")
        if handler is None:  # pragma: no cover — registry always has goal_loop
            raise ValueError("goal_loop execution handler is not registered")
        return handler.start(session_config)


class E2BRunner:
    """E2B cloud sandbox. SDK imported lazily; auth via ``E2B_API_KEY``."""

    kind = "e2b"

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def run(self, cmd, *, timeout: int = 300):  # pragma: no cover - needs live creds (L3)
        from e2b import Sandbox  # lazy: never imported unless a cloud run is chosen

        sbx = Sandbox.create(timeout=timeout)
        try:
            # SECURITY (24-fix, MAJOR 10): E2B ``commands.run`` executes its argument
            # in a SHELL, so a bare ``" ".join(cmd)`` let a metacharacter in any arg
            # (``;`` / ``&&`` / ``$()``) inject extra commands. ``shlex.join`` quotes
            # every token so the argv is passed as literal data, not shell syntax.
            return sbx.commands.run(shlex.join(cmd))
        finally:
            sbx.kill()

    def execute(self, session_config: dict):
        """Run the session's command in an ephemeral E2B cloud sandbox — UNLESS the
        session requires goal-loop/PSM semantics this cmd-only runner cannot honor,
        in which case fall back to the LOCAL goal-loop (24-fix, BLOCKER 3: honest
        routing — never run a degraded cmd-only stub while the caller believes a
        governed goal-loop ran)."""
        if _requires_goal_loop(session_config):
            logger.warning(
                "E2BRunner cannot honor goal-loop/PSM semantics; falling back to the "
                "LOCAL goal-loop for this session (no cmd-only cloud stub)."
            )
            return LocalRunner(self.config).execute(session_config)
        result = self.run(list(session_config.get("cmd") or []))  # pragma: no cover - live creds
        return {  # pragma: no cover - needs live creds (L3)
            "session_id": f"{self.kind}-{uuid.uuid4().hex[:8]}",
            "runner": self.kind,
            "result": result,
        }


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
            # SECURITY (24-fix, MAJOR 10): pass argv DIRECTLY to ``exec`` — no shell.
            # The old ``exec("bash", "-lc", " ".join(cmd))`` ran the joined string
            # through ``bash -lc``, so a metacharacter in any arg injected commands.
            # ``exec(*cmd)`` runs the program with its args verbatim, no shell parse.
            proc = sb.exec(*cmd, timeout=timeout)
            return proc
        finally:
            sb.terminate()

    def execute(self, session_config: dict):
        """Run the session's command in an ephemeral Modal cloud sandbox — UNLESS the
        session requires goal-loop/PSM semantics this cmd-only runner cannot honor,
        in which case fall back to the LOCAL goal-loop (24-fix, BLOCKER 3: honest
        routing — never run a degraded cmd-only stub while the caller believes a
        governed goal-loop ran)."""
        if _requires_goal_loop(session_config):
            logger.warning(
                "ModalRunner cannot honor goal-loop/PSM semantics; falling back to the "
                "LOCAL goal-loop for this session (no cmd-only cloud stub)."
            )
            return LocalRunner(self.config).execute(session_config)
        result = self.run(list(session_config.get("cmd") or []))  # pragma: no cover - live creds
        return {  # pragma: no cover - needs live creds (L3)
            "session_id": f"{self.kind}-{uuid.uuid4().hex[:8]}",
            "runner": self.kind,
            "result": result,
        }


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
