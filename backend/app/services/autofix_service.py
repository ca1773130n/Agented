"""Autofix engine for system errors.

Two tiers:
- Tier 1: Predefined safe operations matched by regex on category:message
- Tier 2: Agent investigation via sa-system super agent
"""

import datetime
import logging
import re
import subprocess
import time
from typing import Callable, Optional

from app.db.system_errors import (
    create_fix_attempt,
    get_system_error,
    update_fix_attempt,
    update_system_error_status,
)
from app.models.system import ErrorStatus, FixStatus

logger = logging.getLogger(__name__)


def _now() -> str:
    """Return current UTC timestamp as ISO string."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# --- Tier 1 fix functions ---


def _fix_cliproxy_not_running(error: dict) -> dict:
    """Attempt to start CLIProxyAPI and verify it's running."""
    try:
        subprocess.Popen(
            ["cliproxyapi"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        import httpx

        resp = httpx.get("http://localhost:8317/health", timeout=5)
        if resp.status_code == 200:
            return {
                "success": True,
                "action_taken": "Started CLIProxyAPI process, health check passed",
            }
        return {"success": False, "action_taken": "Started CLIProxyAPI but health check failed"}
    except Exception as e:
        return {"success": False, "action_taken": f"Failed to start CLIProxyAPI: {e}"}


def _fix_rate_limited(error: dict) -> dict:
    """Log rate limit error — manual intervention needed for account rotation."""
    return {
        "success": False,
        "action_taken": "Rate limit detected. Manual account rotation may be required.",
    }


def _fix_db_locked(error: dict) -> dict:
    """Retry with exponential backoff using fresh connections."""
    from app.db.connection import get_connection

    delays = [0.1, 0.5, 2.0]
    for i, delay in enumerate(delays):
        try:
            time.sleep(delay)
            with get_connection() as conn:
                conn.execute("SELECT 1")
            return {
                "success": True,
                "action_taken": f"DB lock resolved after {i + 1} retries ({delay}s delay)",
            }
        except Exception:
            continue
    return {"success": False, "action_taken": "DB still locked after 3 retries"}


def _fix_stale_session(error: dict) -> dict:
    """Delete stale session and create a fresh one."""
    try:
        import json

        context = json.loads(error.get("context_json") or "{}")
        session_id = context.get("session_id")
        super_agent_id = context.get("super_agent_id")
        if not session_id or not super_agent_id:
            return {
                "success": False,
                "action_taken": "Missing session_id or super_agent_id in context",
            }

        from app.db.connection import get_connection

        with get_connection() as conn:
            conn.execute("DELETE FROM super_agent_sessions WHERE id = ?", (session_id,))
            conn.commit()

        from app.services.super_agent_session_service import SuperAgentSessionService

        new_session_id = SuperAgentSessionService.get_or_create_session(super_agent_id)
        return {
            "success": True,
            "action_taken": (
                f"Deleted stale session {session_id}, created new session {new_session_id}"
            ),
        }
    except Exception as e:
        return {"success": False, "action_taken": f"Failed to fix stale session: {e}"}


# --- Fix Registry ---

FIX_REGISTRY: dict[str, Callable] = {
    r"proxy_error:.*Could not connect.*8317": _fix_cliproxy_not_running,
    r"cli_error:.*rate.limit|429": _fix_rate_limited,
    r"db_error:.*database is locked": _fix_db_locked,
    r"streaming_error:.*session.*stale": _fix_stale_session,
}


def _find_tier1_fix(category: str, message: str) -> Optional[Callable]:
    """Find a matching Tier 1 fix function for the error."""
    key = f"{category}:{message}"
    for pattern, fix_fn in FIX_REGISTRY.items():
        if re.search(pattern, key, re.IGNORECASE):
            return fix_fn
    return None


# --- Tier 2: Agent investigation ---


def _run_tier2_investigation(error_id: str, fix_attempt_id: str, error: dict) -> None:
    """Send error to sa-system agent for investigation."""
    try:
        from app.services.streaming_helper import run_streaming_response
        from app.services.super_agent_session_service import SuperAgentSessionService

        session_id = SuperAgentSessionService.get_or_create_session("sa-system")

        # Build investigation prompt
        context_str = error.get("context_json") or "None"
        prompt = f"""[SYSTEM ERROR - AUTOFIX REQUEST]
An error occurred in the Agented platform that needs investigation.

Error ID: {error.get("id")}
Category: {error.get("category")}
Message: {error.get("message")}
Stack Trace: {error.get("stack_trace") or "None"}
Context: {context_str}

Investigate this error. You have access to the Agented codebase at the current working directory.
Diagnose the root cause, apply a fix if possible, and report what you did.
[END SYSTEM ERROR]"""

        # Send via the session service (handles message storage + token tracking)
        SuperAgentSessionService.send_message(session_id, prompt)

        # Mark as running BEFORE launching streaming
        update_fix_attempt(fix_attempt_id, FixStatus.RUNNING.value, agent_session_id=session_id)

        def on_complete():
            update_fix_attempt(
                fix_attempt_id,
                FixStatus.SUCCESS.value,
                "Agent investigation completed",
                _now(),
            )
            update_system_error_status(error_id, ErrorStatus.FIXED.value)

        def on_error(err_msg):
            update_fix_attempt(
                fix_attempt_id,
                FixStatus.FAILED.value,
                f"Agent investigation failed: {err_msg}",
                _now(),
            )
            update_system_error_status(error_id, ErrorStatus.NEW.value)

        run_streaming_response(
            session_id=session_id,
            super_agent_id="sa-system",
            backend="claude",
            on_complete=on_complete,
            on_error=on_error,
        )

    except Exception as e:
        logger.exception("Tier 2 investigation failed for error %s", error_id)
        update_fix_attempt(
            fix_attempt_id,
            FixStatus.FAILED.value,
            f"Failed to start investigation: {e}",
            _now(),
        )
        update_system_error_status(error_id, ErrorStatus.NEW.value)


# --- Main trigger ---


def trigger_autofix(error_id: str) -> None:
    """Trigger autofix for a system error. Called by capture_error()."""
    try:
        error = get_system_error(error_id)
        if not error:
            logger.error("Cannot trigger autofix: error %s not found", error_id)
            return

        if error.get("status") == ErrorStatus.IGNORED.value:
            logger.debug("Skipping autofix for ignored error %s", error_id)
            return

        category = error["category"]
        message = error["message"]

        # Try Tier 1 first
        fix_fn = _find_tier1_fix(category, message)

        if fix_fn:
            fix_attempt_id = create_fix_attempt(error_id, tier=1)
            if not fix_attempt_id:
                return
            update_system_error_status(error_id, ErrorStatus.INVESTIGATING.value)
            update_fix_attempt(fix_attempt_id, FixStatus.RUNNING.value)

            try:
                result = fix_fn(error)
                if result.get("success"):
                    update_fix_attempt(
                        fix_attempt_id,
                        FixStatus.SUCCESS.value,
                        result.get("action_taken"),
                        _now(),
                    )
                    update_system_error_status(error_id, ErrorStatus.FIXED.value)
                else:
                    update_fix_attempt(
                        fix_attempt_id,
                        FixStatus.FAILED.value,
                        result.get("action_taken"),
                        _now(),
                    )
                    update_system_error_status(error_id, ErrorStatus.NEW.value)
            except Exception as e:
                update_fix_attempt(
                    fix_attempt_id,
                    FixStatus.FAILED.value,
                    f"Fix function raised: {e}",
                    _now(),
                )
                update_system_error_status(error_id, ErrorStatus.NEW.value)
        else:
            # Tier 2: Agent investigation
            fix_attempt_id = create_fix_attempt(error_id, tier=2)
            if not fix_attempt_id:
                return
            update_system_error_status(error_id, ErrorStatus.INVESTIGATING.value)
            _run_tier2_investigation(error_id, fix_attempt_id, error)

    except Exception:
        logger.exception("trigger_autofix failed for error %s", error_id)
