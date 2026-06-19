"""RalphMonitorService -- DEPRECATED (v0.6.0 unified loops).

Ralph is now a thin profile over the goal-loop executor (``goal_loop_runner``),
which owns iteration tracking, the stagnation circuit breaker, and termination.
The git-commit no-progress signal that used to live here has been extracted to
``app.services.loop_progress`` and is consumed directly by the executor's
stagnation exit.

This module is retained only as a thin no-op shim so any lingering import does
not break; it has no live behavior and should not be wired into new code.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RalphMonitorService:
    """Deprecated no-op shim. See ``goal_loop_runner`` + ``loop_progress``.

    The Ralph side-monitor was retired when Ralph was deep-unified onto the
    goal-loop executor. All methods are inert: starting/stopping a monitor is a
    no-op and ``get_state`` always returns ``None`` (callers should read the
    runner state via ``goal_loop_runner.get_runner_state`` instead).
    """

    @classmethod
    def start_monitoring(cls, *args, **kwargs) -> None:
        """No-op. Iteration tracking now lives in the goal-loop executor."""
        logger.debug("RalphMonitorService.start_monitoring is deprecated; ignored.")

    @classmethod
    def stop_monitoring(cls, *args, **kwargs) -> None:
        """No-op. The executor owns the runner thread lifecycle."""
        logger.debug("RalphMonitorService.stop_monitoring is deprecated; ignored.")

    @classmethod
    def get_state(cls, session_id: str) -> Optional[dict]:
        """Always ``None``; read ``goal_loop_runner.get_runner_state`` instead."""
        return None
