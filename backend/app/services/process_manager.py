"""Process manager for tracking and cancelling running trigger executions."""

import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Auto-cancel paused executions after this many seconds (default 30 minutes).
PAUSE_TIMEOUT = int(os.environ.get("PAUSE_TIMEOUT_SECS", "1800"))


@dataclass
class ProcessInfo:
    """Info about a tracked subprocess."""

    process: subprocess.Popen
    pgid: int
    execution_id: str
    trigger_id: str
    paused_at: Optional[float] = None
    pause_timer: Optional[threading.Timer] = field(default=None, repr=False)


class ProcessManager:
    """Singleton manager for tracking running processes for cancellation and shutdown."""

    _processes: Dict[str, ProcessInfo] = {}
    _cancelled: set = set()
    _lock = threading.Lock()

    @classmethod
    def register(cls, execution_id: str, process: subprocess.Popen, trigger_id: str):
        """Register a running process for tracking."""
        with cls._lock:
            try:
                pgid = os.getpgid(process.pid)
            except ProcessLookupError:
                pgid = process.pid  # Fallback if process already exited between Popen and register
                logger.warning(
                    "Process %d exited before pgid lookup for execution %s; "
                    "using pid as pgid fallback — kill signals to this pgid may fail silently",
                    process.pid,
                    execution_id,
                )
            cls._processes[execution_id] = ProcessInfo(
                process=process,
                pgid=pgid,
                execution_id=execution_id,
                trigger_id=trigger_id,
            )
        logger.info(
            f"Registered process for execution {execution_id} (pid={process.pid}, pgid={pgid})"
        )

    @classmethod
    def cancel(cls, execution_id: str) -> bool:
        """Cancel a running execution by killing its process group. Returns True if killed."""
        with cls._lock:
            info = cls._processes.get(execution_id)
            cls._cancelled.add(execution_id)
        if not info:
            return False
        try:
            os.killpg(info.pgid, signal.SIGKILL)
            logger.info(f"Killed process group {info.pgid} for execution {execution_id}")
            return True
        except ProcessLookupError:
            logger.info(f"Process group {info.pgid} already dead for execution {execution_id}")
            return True  # Already dead counts as success
        except Exception as e:
            logger.error(f"Failed to kill process group {info.pgid}: {e}", exc_info=True)
            return False

    @classmethod
    def cancel_graceful(cls, execution_id: str, sigterm_timeout: float = 10.0) -> bool:
        """Gracefully cancel: send SIGTERM then SIGKILL after timeout. Returns True if signal sent."""
        with cls._lock:
            info = cls._processes.get(execution_id)
            cls._cancelled.add(execution_id)
        if not info:
            return False
        try:
            os.killpg(info.pgid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM to process group {info.pgid} for execution {execution_id}")

            # Schedule SIGKILL fallback if process does not exit within sigterm_timeout
            def _force_kill():
                try:
                    if info.process.poll() is None:
                        os.killpg(info.pgid, signal.SIGKILL)
                        logger.info(
                            f"SIGTERM timed out; force-killed process group "
                            f"{info.pgid} for execution {execution_id}"
                        )
                except ProcessLookupError:
                    pass  # Process already gone — expected, safe to ignore
                except OSError as e:
                    logger.error(
                        "Force-kill of process group %d failed (OS error) for execution %s: %s",
                        info.pgid,
                        execution_id,
                        e,
                    )
                except Exception as e:
                    logger.error(f"Force-kill failed for execution {execution_id}: {e}")

            timer = threading.Timer(sigterm_timeout, _force_kill)
            timer.daemon = True
            timer.start()
            return True
        except ProcessLookupError:
            logger.info(f"Process group {info.pgid} already dead for execution {execution_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send SIGTERM to process group {info.pgid}: {e}", exc_info=True)
            return False

    @classmethod
    def is_cancelled(cls, execution_id: str) -> bool:
        """Check if an execution was cancelled."""
        with cls._lock:
            return execution_id in cls._cancelled

    @classmethod
    def pause(cls, execution_id: str) -> bool:
        """Pause a running execution via SIGSTOP. Returns True if paused successfully."""
        from ..db.triggers import update_execution_status_cas

        with cls._lock:
            info = cls._processes.get(execution_id)
        if not info:
            return False

        # CAS: only pause if currently running (prevents race with completion)
        if not update_execution_status_cas(execution_id, "paused", expected_status="running"):
            logger.info(f"CAS failed for pause on execution {execution_id} (not running)")
            return False

        try:
            os.killpg(info.pgid, signal.SIGSTOP)
            logger.info(f"Sent SIGSTOP to process group {info.pgid} for execution {execution_id}")
        except ProcessLookupError:
            logger.warning(f"Process group {info.pgid} already dead when pausing {execution_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to send SIGSTOP to pgid {info.pgid}: {e}", exc_info=True)
            return False

        with cls._lock:
            info.paused_at = time.time()
            # Schedule auto-cancel after PAUSE_TIMEOUT
            timer = threading.Timer(PAUSE_TIMEOUT, cls._auto_cancel_paused, args=[execution_id])
            timer.daemon = True
            timer.start()
            info.pause_timer = timer

        # Broadcast paused status via SSE
        try:
            from .execution_log_service import ExecutionLogService

            ExecutionLogService._broadcast(
                execution_id, "status", {"status": "paused", "execution_id": execution_id}
            )
        except Exception as e:
            logger.debug("Could not broadcast pause status: %s", e)

        return True

    @classmethod
    def resume(cls, execution_id: str) -> bool:
        """Resume a paused execution via SIGCONT. Returns True if resumed successfully."""
        from ..db.triggers import update_execution_status_cas

        with cls._lock:
            info = cls._processes.get(execution_id)
        if not info:
            return False

        # CAS: only resume if currently paused
        if not update_execution_status_cas(execution_id, "running", expected_status="paused"):
            logger.info(f"CAS failed for resume on execution {execution_id} (not paused)")
            return False

        try:
            os.killpg(info.pgid, signal.SIGCONT)
            logger.info(f"Sent SIGCONT to process group {info.pgid} for execution {execution_id}")
        except ProcessLookupError:
            logger.warning(f"Process group {info.pgid} already dead when resuming {execution_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to send SIGCONT to pgid {info.pgid}: {e}", exc_info=True)
            return False

        with cls._lock:
            # Cancel the auto-cancel timer
            if info.pause_timer is not None:
                info.pause_timer.cancel()
                info.pause_timer = None
            info.paused_at = None

        # Broadcast resumed status via SSE
        try:
            from .execution_log_service import ExecutionLogService

            ExecutionLogService._broadcast(
                execution_id, "status", {"status": "running", "execution_id": execution_id}
            )
        except Exception as e:
            logger.debug("Could not broadcast resume status: %s", e)

        return True

    @classmethod
    def _auto_cancel_paused(cls, execution_id: str):
        """Auto-cancel a paused execution after PAUSE_TIMEOUT. Called by timer thread."""
        from ..db.triggers import update_execution_status_cas

        logger.info(f"Auto-cancel timer fired for paused execution {execution_id}")

        with cls._lock:
            info = cls._processes.get(execution_id)
        if not info:
            return

        # Check if still paused via CAS
        if not update_execution_status_cas(
            execution_id, "pause_timeout", expected_status="paused"
        ):
            logger.info(
                f"Execution {execution_id} no longer paused when auto-cancel fired, skipping"
            )
            return

        # Must SIGCONT before SIGTERM — stopped processes cannot receive SIGTERM
        try:
            os.killpg(info.pgid, signal.SIGCONT)
            logger.info(
                f"Sent SIGCONT before cancel for auto-cancel of execution {execution_id}"
            )
        except ProcessLookupError:
            logger.info(f"Process already dead during auto-cancel of {execution_id}")
            return
        except Exception as e:
            logger.error(f"SIGCONT failed during auto-cancel of {execution_id}: {e}")

        # Now gracefully cancel
        cls._cancelled.add(execution_id)
        try:
            os.killpg(info.pgid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM for auto-cancel of execution {execution_id}")

            def _force_kill():
                try:
                    if info.process.poll() is None:
                        os.killpg(info.pgid, signal.SIGKILL)
                        logger.info(f"Force-killed execution {execution_id} after auto-cancel")
                except (ProcessLookupError, OSError):
                    pass

            kill_timer = threading.Timer(10.0, _force_kill)
            kill_timer.daemon = True
            kill_timer.start()
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error(f"SIGTERM failed during auto-cancel of {execution_id}: {e}")

        with cls._lock:
            info.pause_timer = None
            info.paused_at = None

    @classmethod
    def is_paused(cls, execution_id: str) -> bool:
        """Check if an execution is currently paused."""
        with cls._lock:
            info = cls._processes.get(execution_id)
            return info is not None and info.paused_at is not None

    @classmethod
    def cleanup(cls, execution_id: str):
        """Remove a process from tracking (called after process exits)."""
        with cls._lock:
            info = cls._processes.pop(execution_id, None)
            if info and info.pause_timer is not None:
                info.pause_timer.cancel()
            cls._cancelled.discard(execution_id)

    @classmethod
    def get_active_count(cls) -> int:
        """Get the number of actively tracked processes."""
        with cls._lock:
            return len(cls._processes)

    @classmethod
    def get_active_executions(cls) -> list:
        """Get list of active execution IDs."""
        with cls._lock:
            return list(cls._processes.keys())

    @classmethod
    def cancel_all(cls, timeout: int = 300):
        """Wait for all processes to complete, then force-kill after timeout. For graceful shutdown."""
        with cls._lock:
            active = list(cls._processes.values())
        if not active:
            logger.info("No active processes to clean up during shutdown")
            return

        logger.info(
            f"Shutdown: waiting for {len(active)} active execution(s) to complete (timeout={timeout}s)"
        )
        per_process_timeout = max(1, timeout // len(active))
        for info in active:
            try:
                info.process.wait(timeout=per_process_timeout)
                logger.info(f"Execution {info.execution_id} completed during shutdown")
            except subprocess.TimeoutExpired:
                logger.warning(
                    f"Execution {info.execution_id} timed out during shutdown, force-killing"
                )
                try:
                    os.killpg(info.pgid, signal.SIGKILL)
                except ProcessLookupError as e:
                    logger.debug("Process already exited during shutdown: %s", e)
                except Exception as e:
                    logger.error(f"Failed to force-kill {info.execution_id}: {e}")
