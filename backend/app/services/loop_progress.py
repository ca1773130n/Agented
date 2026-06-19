# backend/app/services/loop_progress.py
"""Shared no-progress signals for the unified loop executor.

agent_task loops (Ralph) detect progress via new git commits; the helper is
extracted from the retired RalphMonitorService so the executor — not a side
monitor — decides stagnation.
"""

from __future__ import annotations

import subprocess
from typing import Optional


def head_commit(cwd: str) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def made_progress(prev: Optional[str], current: Optional[str]) -> bool:
    """True when the HEAD commit advanced (a new commit landed this iteration)."""
    return bool(current) and current != prev
