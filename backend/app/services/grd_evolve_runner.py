"""GRD evolve runner (v0.7.88).

Background thread that runs alongside a ``gd evolve`` project
session. ``gd evolve`` writes ``.planning/EVOLVE-STATE.json`` at
the start of each iteration and after every group execution;
this runner polls the file, hashes it, and on change pushes the
new snapshot through ``upsert_evolve_state`` so the operator UI
sees live progress without shelling out to the CLI.

Decoupled from ``ProjectSessionManager`` so PSM stays the pure
stdout/stdin broker — the evolve-specific polling lives here.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from app.db import (
    finalize_evolve_run,
    get_evolve_run_by_session,
    upsert_evolve_state,
)

from .project_session_manager import ProjectSessionManager

logger = logging.getLogger(__name__)


# Polling interval. Tight enough that the UI's "current iteration"
# stays fresh; loose enough that 50 concurrent runs don't thrash
# the filesystem.
_POLL_SECONDS = float(os.environ.get("GRD_EVOLVE_POLL_SECONDS", "10"))

# Hard cap on per-run wall time. ``gd evolve --infinite`` is the
# user's explicit "no cap" — we still bound at 24h to keep
# orphaned threads from leaking. Override via env if needed.
_MAX_WALL_SECONDS = int(os.environ.get("GRD_EVOLVE_MAX_WALL_SECONDS", str(24 * 3600)))


_runners: dict[str, threading.Event] = {}
_runners_lock = threading.Lock()


def start_evolve_state_sync(session_id: str, planning_dir: str) -> None:
    """Spawn the poller thread for a session. Idempotent — calling
    twice for the same session is a no-op (the existing thread
    keeps running).
    """
    with _runners_lock:
        if session_id in _runners:
            return
        stop_event = threading.Event()
        _runners[session_id] = stop_event
    thread = threading.Thread(
        target=_run,
        args=(session_id, planning_dir, stop_event),
        name=f"grd-evolve-sync-{session_id}",
        daemon=False,
    )
    thread.start()


def stop_evolve_state_sync(session_id: str) -> None:
    """Signal the poller thread to exit. Safe to call multiple
    times; never raises.
    """
    with _runners_lock:
        ev = _runners.get(session_id)
    if ev:
        ev.set()


def _run(session_id: str, planning_dir: str, stop_event: threading.Event) -> None:
    """Polling loop. Exits on:
    * ``stop_event`` set (external stop)
    * underlying PSM session ended (``status != 'active'``)
    * wall-time cap reached
    """
    state_file = Path(planning_dir) / "EVOLVE-STATE.json"
    started_at = time.time()
    last_hash: Optional[str] = None
    try:
        while not stop_event.is_set():
            # Bail on session end so the thread doesn't outlive
            # the subprocess by hours.
            info = ProjectSessionManager.get_session_info(session_id)
            if not info or info.get("status") != "active":
                break
            if time.time() - started_at > _MAX_WALL_SECONDS:
                logger.warning(
                    "grd_evolve: poller for %s exceeded wall cap; exiting",
                    session_id,
                )
                break

            try:
                if state_file.is_file():
                    content = state_file.read_text(encoding="utf-8")
                    file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    if file_hash != last_hash:
                        last_hash = file_hash
                        _on_state_change(session_id, content)
            except Exception:
                # Read / parse failures are non-fatal — log and
                # try again next tick. EVOLVE-STATE.json may be
                # mid-write when we sample it.
                logger.warning(
                    "grd_evolve: state read failed for %s",
                    session_id,
                    exc_info=True,
                )

            stop_event.wait(timeout=_POLL_SECONDS)
    finally:
        with _runners_lock:
            _runners.pop(session_id, None)


def _on_state_change(session_id: str, content: str) -> None:
    """Push the new EVOLVE-STATE snapshot to the DB and broadcast
    a small SSE event so any subscribed UI updates in real time.
    """
    iteration = 0
    try:
        parsed = json.loads(content)
        iteration = int(parsed.get("iteration") or 0)
    except (json.JSONDecodeError, ValueError, TypeError):
        # Treat malformed JSON as an empty snapshot; the row's
        # ``last_state_json`` still carries the raw bytes so the
        # UI can show "syncing…" rather than blank.
        logger.warning(
            "grd_evolve: EVOLVE-STATE.json for %s was not valid JSON; storing raw bytes anyway",
            session_id,
        )

    updated = upsert_evolve_state(
        session_id=session_id,
        iteration=iteration,
        state_json=content,
    )
    if not updated:
        # No grd_evolve_runs row matches — happens during the
        # tiny gap between session creation and the row insert in
        # the handler. We'll catch the next tick.
        logger.debug(
            "grd_evolve: no run row yet for session %s; skipping broadcast",
            session_id,
        )
        return
    ProjectSessionManager._broadcast(
        session_id,
        "grd_evolve_state",
        {
            "iteration": iteration,
            "synced_at": datetime.datetime.utcnow().isoformat(),
        },
    )


def finalize_on_session_exit(session_id: str, exit_code: Optional[int]) -> None:
    """Called by ``ProjectSessionManager._handle_session_exit`` when
    a ``grd_evolve``-typed session ends. Stops the poller (if
    running) and marks the run row terminal so the UI flips out
    of "active".
    """
    stop_evolve_state_sync(session_id)
    if get_evolve_run_by_session(session_id) is None:
        return
    if exit_code is None or exit_code == 0:
        finalize_evolve_run(session_id=session_id, status="completed")
    else:
        finalize_evolve_run(
            session_id=session_id,
            status="failed",
            error_message=f"gd evolve exited with code {exit_code}",
        )
