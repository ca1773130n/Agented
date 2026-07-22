"""Supervised Tesserae engine daemon — the 0.23/0.24 "sleep cycle".

``tesserae engine --all --consolidate`` is a *long-lived* process. On idle it
compresses agent memory (0.23) and — the 0.24 additions — forgets-by-disuse via
LRU decay and discovers cross-agent connections via the ``associate`` pass.
Agented's other engine path (``engine --all --once``, see
:func:`tesserae_integration.engine_refresh_async`) is a one-shot recompile DRAIN
that *skips consolidation by design*, so the sleep cycle needs this persistent
supervisor.

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
# The exact argv tail we spawn — also the pkill match for orphan cleanup.
_ENGINE_ARGS = ["engine", "--all", "--consolidate"]


def _enabled() -> bool:
    # Default ON — the operator opted into the full sleep cycle; opt out with =0.
    return os.environ.get("AGENTED_TESSERAE_CONSOLIDATE", "1").strip().lower() in _TRUTHY


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
            logger.info(
                "Tesserae consolidation daemon disabled (AGENTED_TESSERAE_CONSOLIDATE=0)"
            )
            return False
        with cls._lock:
            if cls._process is not None and cls._process.poll() is None:
                return True
            cls.kill_orphans()
            # ``TESSERAE_AGENT_DISTILL=1`` is the same opt-in gate ``distill`` uses;
            # without it consolidation no-ops. The LLM backend resolves from the
            # harness config dir (CLAUDE_CONFIG_DIR), never a raw inference key, so
            # honouring AGENTED_SERVER_NO_LLM_KEYS (scrub) stays correct here.
            env = config.subprocess_env(os.environ.copy())
            if env is None:
                env = os.environ.copy()
            env["TESSERAE_AGENT_DISTILL"] = "1"
            cmd = [
                _TESSERAE_CMD,
                *_ENGINE_ARGS,
                "--consolidate-idle",
                str(_IDLE_SECONDS),
                "--consolidate-every",
                str(_CONSOLIDATE_EVERY),
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
                logger.info(
                    "Tesserae consolidation daemon started (pid=%d)", cls._process.pid
                )
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
        }
