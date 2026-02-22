"""Process manager for tracking and cancelling running trigger executions."""

import logging
import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class ProcessInfo:
    """Info about a tracked subprocess."""

    process: subprocess.Popen
    pgid: int
    execution_id: str
    trigger_id: str


class ProcessManager:
    """Singleton manager for tracking running processes for cancellation and shutdown."""

    _processes: Dict[str, ProcessInfo] = {}
    _cancelled: set = set()
    _lock = threading.Lock()

    @classmethod
    def register(cls, execution_id: str, process: subprocess.Popen, trigger_id: str):
        """Register a running process for tracking."""
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            pgid = process.pid  # Fallback if process already exited
        with cls._lock:
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
            logger.error(f"Failed to kill process group {info.pgid}: {e}")
            return False

    @classmethod
    def is_cancelled(cls, execution_id: str) -> bool:
        """Check if an execution was cancelled."""
        with cls._lock:
            return execution_id in cls._cancelled

    @classmethod
    def cleanup(cls, execution_id: str):
        """Remove a process from tracking (called after process exits)."""
        with cls._lock:
            cls._processes.pop(execution_id, None)
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
