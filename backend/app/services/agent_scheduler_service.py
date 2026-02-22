"""Agent execution scheduler service with admission control and hysteresis-damped resume.

Gates agent execution based on rate limit ETA predictions. Uses SQLite-persisted
session states with an in-memory cache for fast eligibility checks. Hysteresis
prevents oscillation when ETA hovers near the safety margin threshold.

Research basis: Admission control pattern (RESEARCH.md Rec 1), SQLite + in-memory
cache pattern (Rec 2), hysteresis for resume damping (Pitfall 1).
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class AgentSchedulerService:
    """Admission controller that gates agent execution based on rate limit ETA predictions.

    All methods are classmethods following the existing service pattern
    (MonitoringService, BudgetService). Thread-safe via _lock for in-memory cache.
    """

    # In-memory cache: {str(account_id): {"state": str, "stop_reason": str, ...}}
    _session_states: dict = {}
    _lock = threading.Lock()

    @classmethod
    def init(cls):
        """Initialize from DB: load existing sessions into _session_states. Called at app startup."""
        from ..database import get_all_agent_sessions

        try:
            sessions = get_all_agent_sessions()
            with cls._lock:
                cls._session_states = {}
                for session in sessions:
                    key = str(session["account_id"])
                    cls._session_states[key] = {
                        "state": session["state"],
                        "stop_reason": session["stop_reason"],
                        "stop_window_type": session["stop_window_type"],
                        "stop_eta_minutes": session["stop_eta_minutes"],
                        "resume_estimate": session["resume_estimate"],
                        "consecutive_safe_polls": session["consecutive_safe_polls"] or 0,
                        "updated_at": session["updated_at"],
                    }
            logger.info(f"AgentSchedulerService initialized with {len(sessions)} session(s)")
        except Exception as e:
            logger.warning(f"Could not initialize agent scheduler from DB: {e}")

    @classmethod
    def check_eligibility(cls, account_id: int) -> dict:
        """Admission control check for a single account.

        Called PER ACCOUNT within the fallback chain loop (not as a blanket check).
        Returns {"eligible": True/False, "reason": str, ...}
        """
        key = str(account_id)
        with cls._lock:
            session = cls._session_states.get(key)

        if session and session["state"] == "stopped":
            return {
                "eligible": False,
                "reason": "scheduler_paused",
                "message": f"Account {account_id} paused by scheduler: {session.get('stop_reason', 'unknown')}",
                "resume_estimate": session.get("resume_estimate"),
            }

        return {"eligible": True, "reason": "ok"}

    @classmethod
    def evaluate_all_accounts(cls, now: datetime = None):
        """Main evaluation loop: check all accounts against rate limit ETAs.

        Called by MonitoringService poll callback (wired in Plan 02).
        Groups windows by account_id, uses most conservative (shortest) ETA per account.
        """
        from ..database import get_monitoring_config
        from .monitoring_service import MonitoringService

        if now is None:
            now = datetime.now(timezone.utc)

        # Load scheduler-related config
        config = get_monitoring_config()
        safety_margin_minutes = config.get("safety_margin_minutes", 5)
        resume_hysteresis_polls = config.get("resume_hysteresis_polls", 2)

        # Get current monitoring status with ETA projections
        status = MonitoringService.get_monitoring_status()
        windows = status.get("windows", [])

        if not windows:
            logger.debug("Scheduler evaluate: no monitoring windows available")
            return

        # Group windows by account_id, find most conservative ETA per account
        account_etas: dict[int, dict] = {}
        for window in windows:
            acct_id = window["account_id"]
            eta = window.get("eta", {})
            eta_status = eta.get("status", "no_data")
            minutes_remaining = eta.get("minutes_remaining")

            if acct_id not in account_etas:
                account_etas[acct_id] = {
                    "eta_status": eta_status,
                    "minutes_remaining": minutes_remaining,
                    "window_type": window.get("window_type"),
                    "resets_at": window.get("resets_at"),
                }
            else:
                # Take most conservative: at_limit > projected (lower minutes) > safe > no_data
                existing = account_etas[acct_id]
                if cls._is_more_conservative(eta_status, minutes_remaining, existing):
                    account_etas[acct_id] = {
                        "eta_status": eta_status,
                        "minutes_remaining": minutes_remaining,
                        "window_type": window.get("window_type"),
                        "resets_at": window.get("resets_at"),
                    }

        # Evaluate each account
        for acct_id, eta_info in account_etas.items():
            eta_status = eta_info["eta_status"]
            minutes_remaining = eta_info["minutes_remaining"]
            window_type = eta_info["window_type"]
            resets_at = eta_info.get("resets_at")

            if eta_status == "at_limit":
                cls._set_state(
                    acct_id,
                    "stopped",
                    stop_reason="at_limit",
                    stop_window_type=window_type,
                    stop_eta_minutes=0,
                    resets_at=resets_at,
                    now=now,
                )
            elif (
                eta_status == "projected"
                and minutes_remaining is not None
                and minutes_remaining < safety_margin_minutes
            ):
                cls._set_state(
                    acct_id,
                    "stopped",
                    stop_reason="approaching_limit",
                    stop_window_type=window_type,
                    stop_eta_minutes=minutes_remaining,
                    resets_at=resets_at,
                    now=now,
                )
            else:
                # Safe, no_data, or projected with enough headroom -> maybe resume
                cls._maybe_resume(acct_id, resume_hysteresis_polls)

        logger.debug(f"Scheduler evaluate complete: {len(account_etas)} account(s) checked")

    @classmethod
    def _is_more_conservative(
        cls,
        new_status: str,
        new_minutes: Optional[float],
        existing: dict,
    ) -> bool:
        """Return True if (new_status, new_minutes) is more conservative than existing."""
        priority = {"at_limit": 4, "projected": 3, "safe": 1, "no_data": 0}
        new_pri = priority.get(new_status, 0)
        old_pri = priority.get(existing["eta_status"], 0)

        if new_pri > old_pri:
            return True
        if new_pri == old_pri and new_pri == 3:
            # Both projected: pick shorter minutes_remaining
            old_min = existing.get("minutes_remaining")
            if new_minutes is not None and (old_min is None or new_minutes < old_min):
                return True
        return False

    @classmethod
    def _set_state(
        cls,
        account_id: int,
        state: str,
        stop_reason: str = None,
        stop_window_type: str = None,
        stop_eta_minutes: float = None,
        resets_at: str = None,
        now: datetime = None,
    ):
        """Update in-memory cache + persist to DB.

        Computes resume_estimate when stopping. Resets consecutive_safe_polls to 0 when stopping.
        """
        from ..database import upsert_agent_session

        if now is None:
            now = datetime.now(timezone.utc)

        key = str(account_id)

        # Compute resume_estimate when stopping
        resume_estimate = None
        consecutive_safe_polls = 0
        if state == "stopped":
            if resets_at:
                resume_estimate = resets_at
            elif stop_eta_minutes is not None:
                resume_estimate = (now + timedelta(minutes=max(stop_eta_minutes, 1))).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
            else:
                resume_estimate = (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
            consecutive_safe_polls = 0  # Reset on stop

        # Log transition
        with cls._lock:
            old_state = cls._session_states.get(key, {}).get("state", "none")
            cls._session_states[key] = {
                "state": state,
                "stop_reason": stop_reason,
                "stop_window_type": stop_window_type,
                "stop_eta_minutes": stop_eta_minutes,
                "resume_estimate": resume_estimate,
                "consecutive_safe_polls": consecutive_safe_polls,
                "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

        if old_state != state:
            logger.info(
                f"Scheduler: account {account_id} state {old_state} -> {state} "
                f"(reason: {stop_reason})"
            )

        # Persist to DB (outside lock -- DB has its own locking via busy_timeout)
        upsert_agent_session(
            account_id=account_id,
            state=state,
            stop_reason=stop_reason,
            stop_window_type=stop_window_type,
            stop_eta_minutes=stop_eta_minutes,
            resume_estimate=resume_estimate,
            consecutive_safe_polls=consecutive_safe_polls,
        )

    @classmethod
    def _maybe_resume(cls, account_id: int, hysteresis_polls: int):
        """Hysteresis-damped resume: only resume after N consecutive safe polls.

        Prevents oscillation when ETA hovers near the safety margin threshold.
        """
        from ..database import upsert_agent_session

        key = str(account_id)
        with cls._lock:
            session = cls._session_states.get(key)
            if not session or session["state"] != "stopped":
                return

            polls = session.get("consecutive_safe_polls", 0) + 1

            if polls >= hysteresis_polls:
                # Resume: transition stopped -> queued
                session["state"] = "queued"
                session["stop_reason"] = None
                session["stop_window_type"] = None
                session["stop_eta_minutes"] = None
                session["resume_estimate"] = None
                session["consecutive_safe_polls"] = 0
                new_state = "queued"
                new_polls = 0
            else:
                # Not enough safe polls yet: increment counter, stay stopped
                session["consecutive_safe_polls"] = polls
                new_state = "stopped"
                new_polls = polls

        if new_state == "queued":
            logger.info(
                f"Scheduler: account {account_id} state stopped -> queued "
                f"(hysteresis: {hysteresis_polls} safe polls reached)"
            )
        else:
            logger.debug(
                f"Scheduler: account {account_id} still stopped "
                f"(safe polls: {polls}/{hysteresis_polls})"
            )

        # Persist to DB (outside lock)
        with cls._lock:
            current = cls._session_states.get(key, {})
        upsert_agent_session(
            account_id=account_id,
            state=current.get("state", new_state),
            stop_reason=current.get("stop_reason"),
            stop_window_type=current.get("stop_window_type"),
            stop_eta_minutes=current.get("stop_eta_minutes"),
            resume_estimate=current.get("resume_estimate"),
            consecutive_safe_polls=current.get("consecutive_safe_polls", new_polls),
        )

    @classmethod
    def get_scheduler_status(cls) -> dict:
        """Return comprehensive scheduler status for the API."""
        from ..database import get_connection, get_monitoring_config

        config = get_monitoring_config()

        # Build account_id -> name map
        account_names: dict[int, str] = {}
        try:
            with get_connection() as conn:
                rows = conn.execute("SELECT id, account_name FROM backend_accounts").fetchall()
                account_names = {row["id"]: row["account_name"] for row in rows}
        except Exception:
            pass  # Graceful degradation -- show IDs if lookup fails

        with cls._lock:
            sessions = []
            summary = {"total": 0, "queued": 0, "running": 0, "stopped": 0}
            for key, session in cls._session_states.items():
                sessions.append(
                    {
                        "account_id": int(key),
                        "account_name": account_names.get(int(key), f"Account {key}"),
                        "state": session["state"],
                        "stop_reason": session.get("stop_reason"),
                        "stop_window_type": session.get("stop_window_type"),
                        "stop_eta_minutes": session.get("stop_eta_minutes"),
                        "resume_estimate": session.get("resume_estimate"),
                        "consecutive_safe_polls": session.get("consecutive_safe_polls", 0),
                        "updated_at": session.get("updated_at"),
                    }
                )
                summary["total"] += 1
                state = session["state"]
                if state in summary:
                    summary[state] += 1

        return {
            "enabled": config.get("enabled", False),
            "safety_margin_minutes": config.get("safety_margin_minutes", 5),
            "resume_hysteresis_polls": config.get("resume_hysteresis_polls", 2),
            "sessions": sessions,
            "global_summary": summary,
        }

    @classmethod
    def get_session_for_account(cls, account_id: int) -> dict | None:
        """Return session state for one account from cache."""
        key = str(account_id)
        with cls._lock:
            session = cls._session_states.get(key)
            if session:
                return {
                    "account_id": account_id,
                    **session,
                }
        return None

    @classmethod
    def mark_running(cls, account_id: int):
        """Execution lifecycle hook: called BEFORE starting execution on an account.

        Transitions queued -> running. Creates session in running state if none exists.
        Does NOT change stopped state (stopped takes priority as a defensive guard).
        """
        key = str(account_id)
        with cls._lock:
            session = cls._session_states.get(key)

        if session and session["state"] == "stopped":
            logger.info(
                f"Scheduler: mark_running called for stopped account {account_id}, "
                f"keeping stopped state (defensive guard)"
            )
            return

        cls._set_state(account_id, "running")
        logger.info(f"Scheduler: account {account_id} marked running")

    @classmethod
    def mark_completed(cls, account_id: int):
        """Execution lifecycle hook: called AFTER execution finishes on an account.

        Transitions running -> queued. Preserves stopped state (scheduler may have
        stopped this account while execution was in progress).
        """
        key = str(account_id)
        with cls._lock:
            session = cls._session_states.get(key)

        if not session:
            # No session: no-op (defensive)
            return

        if session["state"] == "stopped":
            # Stopped state persists even after execution completes (SCHED-03)
            logger.info(
                f"Scheduler: mark_completed for stopped account {account_id}, "
                f"preserving stopped state"
            )
            return

        if session["state"] == "running":
            cls._set_state(account_id, "queued")
            logger.info(f"Scheduler: account {account_id} marked completed -> queued")
            return

        # State is "queued" or unexpected: no-op (defensive)
        logger.debug(
            f"Scheduler: mark_completed for account {account_id} in state "
            f"'{session['state']}', no-op"
        )
