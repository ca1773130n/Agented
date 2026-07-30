"""Supervised Tesserae engine daemon — the 0.23–0.25 "sleep cycle".

``tesserae engine --all --consolidate`` is a *long-lived* process whose idle tick
runs three ops (``engine/daemon.py:_consolidate_once``): DISTILL, then ASSOCIATE
(0.24 — discovers cross-agent connections by embedding similarity, needs the
``[semantic]`` extra), then SUMMARIZE (0.25 — pre-warms community-summary caches
for the most-demanded graph_map scopes, bounded per tick by ``--summarize-budget``;
default 25 LLM calls, ``AGENTED_TESSERAE_SUMMARIZE_BUDGET=0`` disables just that
op). Agented's other engine path (``engine --all --once``, see
:func:`tesserae_integration.engine_refresh_async`) is a one-shot recompile DRAIN
that *skips consolidation by design*, so the sleep cycle needs this persistent
supervisor.

**We run this daemon with DISTILL off** (``TESSERAE_AGENT_DISTILL=0``, see
:meth:`TesseraeEngineDaemon.start`) — agent distillation is owned solely by
:func:`tesserae_integration._maybe_schedule_auto_distill`. ASSOCIATE and
SUMMARIZE are independent of that gate and still run every tick.

Mirrors :class:`cliproxy_manager.CLIProxyManager`: a module-singleton
``subprocess.Popen`` handle (safe only under gunicorn ``workers=1``, the mandated
config), ``kill_orphans`` before start, ``killpg`` on stop, atexit-registered by
:mod:`app_litestar.lifecycle`. Consolidation calls the LLM backend on idle, so
it is gated behind ``AGENTED_TESSERAE_CONSOLIDATE`` (default on) for operators
who want the daemon off.
"""

import os
import signal
import subprocess
import threading
from typing import Optional

from app import config

from .tesserae_integration import _REPO_ROOT, _TESSERAE_CMD, logger

_TRUTHY = {"1", "true", "yes", "on"}

# Tesserae's own defaults (see ``tesserae engine --help``): consolidate after
# 5 min of quiet, with a 6h ceiling. Passed explicitly so the daemon's behaviour
# is legible in `ps`/status rather than implicit in the CLI defaults.
_IDLE_SECONDS = 300
_CONSOLIDATE_EVERY = 21600
# The exact argv tail we spawn — also the pkill match for orphan cleanup. The
# cadence and --summarize-budget flags are appended in start(); this stays the
# 3-token prefix so the kill_orphans() pkill substring keeps matching regardless.
_ENGINE_ARGS = ["engine", "--all", "--consolidate"]
# 0.25 SUMMARIZE budget: max LLM calls/tick spent pre-warming community summaries
# (Tesserae's own default is 25). A recurring background cost, so it's operator-
# tunable; 0 disables just the SUMMARIZE op (the rest of the sleep cycle runs on).
_DEFAULT_SUMMARIZE_BUDGET = 25


def _enabled() -> bool:
    # Default ON — the operator opted into the full sleep cycle; opt out with =0.
    return os.environ.get("AGENTED_TESSERAE_CONSOLIDATE", "1").strip().lower() in _TRUTHY


def _summarize_budget() -> int:
    """Per-tick SUMMARIZE LLM-call budget from AGENTED_TESSERAE_SUMMARIZE_BUDGET
    (default 25). Non-negative int; a bad/negative value falls back to the default,
    0 disables the op. Clamped here so a fat-fingered env can't spend unboundedly."""
    raw = os.environ.get("AGENTED_TESSERAE_SUMMARIZE_BUDGET")
    if raw is None or raw.strip() == "":
        return _DEFAULT_SUMMARIZE_BUDGET
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_SUMMARIZE_BUDGET
    return val if val >= 0 else _DEFAULT_SUMMARIZE_BUDGET


class TesseraeEngineDaemon:
    """Long-lived ``tesserae engine --all --consolidate`` supervisor."""

    _process: Optional[subprocess.Popen] = None
    _lock = threading.Lock()

    @classmethod
    def kill_orphans(cls) -> None:
        """Reap a consolidate daemon left by a prior run (crash/SIGKILL skips
        atexit), so a gunicorn restart never stacks a second sleep cycle."""
        try:
            subprocess.run(
                ["pkill", "-f", "tesserae engine --all --consolidate"],
                capture_output=True,
                timeout=5,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort cleanup
            logger.debug("tesserae engine orphan cleanup: %s", exc)

    @classmethod
    def start(cls) -> bool:
        """Spawn the daemon. Returns True when a live process is running.
        No-op (returns False) when disabled or the binary is missing."""
        if not _enabled():
            logger.info("Tesserae consolidation daemon disabled (AGENTED_TESSERAE_CONSOLIDATE=0)")
            return False
        with cls._lock:
            if cls._process is not None and cls._process.poll() is None:
                return True
            cls.kill_orphans()
            # The LLM backend resolves from the harness config dir
            # (CLAUDE_CONFIG_DIR), never a raw inference key, so honouring
            # AGENTED_SERVER_NO_LLM_KEYS (scrub) stays correct here.
            env = config.subprocess_env(os.environ.copy())
            if env is None:
                env = os.environ.copy()
            # DISTILL off, deliberately. This daemon and Agented's auto-distill
            # policy (tesserae_integration._maybe_schedule_auto_distill) would
            # otherwise both drive agent_distill.distill_agent against the same
            # ``.tesserae/agents/<key>/distilled.graph.json`` in two OS processes,
            # and nothing can serialize them: the daemon's consolidation tick holds
            # only an in-process semaphore (engine/daemon.py:702) and takes no
            # ``.tesserae/compile.lock``, so a lock on our side would be inert.
            # Concurrent runs cost double, can regress the artifact to an older
            # graph's content (last os.replace wins), and race an unWALed
            # DistillStateStore (agent_distill.py:355) with a 5 s busy timeout.
            #
            # Agented's path is the one to keep: it honours the per-project
            # ``projects.tesserae_distill_enabled`` opt-in (the daemon's `--all`
            # ignores it and would spend on every project in the tesserae
            # registry), it dry-run-prices the pass before spending, it refreshes
            # on ANY graph change rather than only under the daemon's memory-
            # pressure floor of half the 48k chunk budget (agent_distill.py:2853),
            # and it survives this daemon being switched off.
            #
            # "0" and not a pop: an explicit env spelling WINS over a project's
            # ``agent_distill.enabled`` config (agent_distill.py:291-293), so this
            # is a hard off for every project the fleet daemon touches.
            env["TESSERAE_AGENT_DISTILL"] = "0"
            cmd = [
                _TESSERAE_CMD,
                *_ENGINE_ARGS,
                "--consolidate-idle",
                str(_IDLE_SECONDS),
                "--consolidate-every",
                str(_CONSOLIDATE_EVERY),
                "--summarize-budget",
                str(_summarize_budget()),
            ]
            try:
                cls._process = subprocess.Popen(
                    cmd,
                    cwd=str(_REPO_ROOT),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env,
                )
                logger.info("Tesserae consolidation daemon started (pid=%d)", cls._process.pid)
                return True
            except FileNotFoundError:
                logger.warning("tesserae binary not found — consolidation daemon not started")
                return False
            except Exception as exc:  # noqa: BLE001 — start failure must not crash boot
                logger.warning("Failed to start tesserae consolidation daemon: %s", exc)
                cls._process = None
                return False

    @classmethod
    def stop(cls) -> None:
        """SIGTERM → (5s) SIGKILL the process group. Idempotent."""
        with cls._lock:
            proc = cls._process
            cls._process = None
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
            logger.info("Stopped tesserae consolidation daemon (pid=%d)", proc.pid)
        except ProcessLookupError:
            logger.debug("tesserae consolidation daemon already exited (pid=%d)", proc.pid)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                logger.debug("daemon exited during SIGKILL (pid=%d)", proc.pid)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error stopping tesserae consolidation daemon: %s", exc, exc_info=True)

    @classmethod
    def status(cls) -> dict:
        """Sleep-cycle state sourced from THIS supervisor — Tesserae's CLI
        exposes no consolidation-status field, so these are the honest facts we
        know (never fabricated): whether it's enabled, whether the process is
        live, and the idle/ceiling cadence it was launched with.

        ``associate`` (0.24) also needs the ``[semantic]`` extra installed into
        the tesserae tool venv; that's a setup concern and not introspectable
        from this process, so it is deliberately not asserted here.
        """
        with cls._lock:
            proc = cls._process
        running = proc is not None and proc.poll() is None
        # ponytail: no restart-on-crash — matches CLIProxyManager (the only other
        # supervised subprocess). A dead daemon just pauses consolidation until
        # the next boot; add a scheduler keepalive if that proves insufficient.
        return {
            "enabled": _enabled(),
            "running": running,
            "idle_seconds": _IDLE_SECONDS,
            "consolidate_every": _CONSOLIDATE_EVERY,
            "summarize_budget": _summarize_budget(),
        }
