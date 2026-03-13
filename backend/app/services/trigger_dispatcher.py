"""Trigger dispatching logic extracted from ExecutionService.

Handles webhook and GitHub event dispatching to matching triggers and teams.
"""

import datetime
import hashlib
import json
import logging
from typing import Optional

from app.config import WEBHOOK_DEDUP_WINDOW

from ..database import (
    get_triggers_by_trigger_source,
    get_webhook_triggers,
)
from ..db.webhook_dedup import check_and_insert_dedup_key
from ..utils.json_path import get_nested_value

logger = logging.getLogger(__name__)


def match_payload(config: dict, payload: dict) -> Optional[str]:
    """Check whether a webhook payload matches a trigger/team config's field criteria.

    Returns the extracted text string if the payload matches, or None if it does not match.
    Text is extracted using text_field_path and normalized to str.
    """
    match_field_path = config.get("match_field_path")
    match_field_value = config.get("match_field_value")
    text_field_path = config.get("text_field_path", "text")
    detection_keyword = config.get("detection_keyword", "")

    if match_field_path and match_field_value:
        actual_value = get_nested_value(payload, match_field_path)
        if str(actual_value) != str(match_field_value):
            return None

    text = get_nested_value(payload, text_field_path)
    if text is None:
        text = ""
    elif not isinstance(text, str):
        text = str(text)

    if detection_keyword and detection_keyword not in text:
        return None

    return text


def dispatch_webhook_event(
    payload: dict,
    raw_payload: bytes = None,
    signature_header: str = None,
    save_trigger_event_fn=None,
) -> bool:
    """Dispatch a webhook event to matching triggers and teams based on configurable field matching.

    Args:
        payload: The JSON webhook payload (parsed dict)
        raw_payload: Raw request body bytes, used for HMAC validation
        signature_header: Value of the X-Webhook-Signature-256 header
        save_trigger_event_fn: Callable to save trigger events (defaults to ExecutionService.save_trigger_event)

    Returns:
        True if at least one trigger or team was triggered
    """
    if save_trigger_event_fn is None:
        from .execution_service import ExecutionService

        save_trigger_event_fn = ExecutionService.save_trigger_event

    triggered = False

    # --- Trigger dispatch ---
    triggers = get_webhook_triggers()
    for trigger in triggers:
        # HMAC validation: if this trigger has a webhook_secret configured,
        # require a valid signature. Skip trigger if signature is missing or invalid.
        webhook_secret = trigger.get("webhook_secret")
        if webhook_secret:
            from .webhook_validation_service import WebhookValidationService

            if raw_payload is None or not WebhookValidationService.validate_signature(
                raw_payload, signature_header or "", webhook_secret
            ):
                logger.warning(
                    "Webhook HMAC validation failed for trigger '%s' (%s); skipping dispatch",
                    trigger["name"],
                    trigger["id"],
                )
                continue

        # Check if payload matches the trigger's field criteria and extract text
        text = match_payload(trigger, payload)
        if text is None:
            continue

        # DB-backed deduplication: skip if identical payload was dispatched within TTL
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        is_new = check_and_insert_dedup_key(
            trigger_id=trigger["id"],
            payload_hash=payload_hash,
            ttl_seconds=WEBHOOK_DEDUP_WINDOW,
        )
        if not is_new:
            logger.info(
                "Webhook dedup: skipping duplicate dispatch for trigger '%s' (DB-backed)",
                trigger["name"],
            )
            continue

        logger.info("Trigger '%s' triggered by webhook", trigger["name"])
        save_trigger_event_fn(trigger, payload)

        # Route to super agent session if dispatch_type is configured
        if trigger.get("dispatch_type") == "super_agent" and trigger.get("super_agent_id"):
            from .super_agent_session_service import (
                SuperAgentSessionService,
                SessionLimitError,
            )
            from ..db.triggers import create_execution_log, update_execution_log
            from ..db.ids import generate_execution_id

            # Render prompt template with matched text
            prompt_template = trigger.get("prompt_template") or "{message}"
            rendered_prompt = prompt_template.replace("{message}", text)

            execution_id = generate_execution_id(trigger["id"])
            started_at = datetime.datetime.now().isoformat()

            try:
                session_id = SuperAgentSessionService.get_or_create_session(
                    trigger["super_agent_id"]
                )
                SuperAgentSessionService.send_message(session_id, rendered_prompt)

                create_execution_log(
                    execution_id=execution_id,
                    trigger_id=trigger["id"],
                    trigger_type="webhook",
                    started_at=started_at,
                    prompt=rendered_prompt,
                    backend_type="super_agent",
                    command="",
                    source_type="super_agent",
                    session_id=session_id,
                )
                logger.info(
                    "Dispatched trigger '%s' to super agent session %s",
                    trigger["name"],
                    session_id,
                )
                triggered = True
            except SessionLimitError as exc:
                create_execution_log(
                    execution_id=execution_id,
                    trigger_id=trigger["id"],
                    trigger_type="webhook",
                    started_at=started_at,
                    prompt=rendered_prompt,
                    backend_type="super_agent",
                    command="",
                    source_type="super_agent",
                )
                update_execution_log(
                    execution_id=execution_id,
                    status="failed",
                    finished_at=datetime.datetime.now().isoformat(),
                    error_message=str(exc),
                )
                logger.warning(
                    "Session limit reached for trigger '%s': %s",
                    trigger["name"],
                    exc,
                )
            continue

        # Enqueue for dispatch via ExecutionQueueService (replaces direct thread spawn)
        from .execution_queue_service import ExecutionQueueService, QueueFullError

        try:
            ExecutionQueueService.enqueue(
                trigger_id=trigger["id"],
                trigger_type="webhook",
                message_text=text,
                event_data=payload,
            )
            triggered = True
        except QueueFullError:
            logger.warning(
                "Queue depth limit exceeded for trigger '%s' (%s); rejecting webhook dispatch",
                trigger["name"],
                trigger["id"],
            )
            continue

    # --- Team dispatch ---
    from ..database import get_webhook_teams

    teams = get_webhook_teams()
    for team in teams:
        # Parse trigger_config for field-matching rules (same schema as triggers)
        trigger_config = team.get("trigger_config")
        if trigger_config and isinstance(trigger_config, str):
            try:
                trigger_config = json.loads(trigger_config)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(
                    "Failed to parse trigger_config JSON for team '%s' (%s): %s — using empty config",
                    team.get("name", ""),
                    team.get("id", ""),
                    e,
                )
                trigger_config = {}
        if not trigger_config:
            trigger_config = {}

        # Check if payload matches the team's field criteria and extract text
        text = match_payload(trigger_config, payload)
        if text is None:
            continue

        logger.info("Team '%s' triggered by webhook", team["name"])

        from .team_execution_service import TeamExecutionService

        TeamExecutionService.execute_team(team["id"], text, payload, "webhook")
        triggered = True

    if not triggered:
        logger.debug("No webhook-triggered triggers or teams matched")

    return triggered


def dispatch_github_event(repo_url: str, pr_data: dict, save_trigger_event_fn=None) -> bool:
    """Dispatch a GitHub PR event to matching triggers and teams.

    Args:
        repo_url: The GitHub repository URL
        pr_data: Dictionary containing PR information:
            - pr_number: PR number
            - pr_title: PR title
            - pr_url: PR URL
            - pr_author: PR author username
            - repo_full_name: Repository full name (owner/repo)
            - action: PR action (opened, synchronize, reopened)
        save_trigger_event_fn: Callable to save trigger events (defaults to ExecutionService.save_trigger_event)

    Returns:
        True if at least one trigger or team was triggered
    """
    if save_trigger_event_fn is None:
        from .execution_service import ExecutionService

        save_trigger_event_fn = ExecutionService.save_trigger_event

    triggered = False

    # --- Trigger dispatch ---
    triggers = get_triggers_by_trigger_source("github")
    for trigger in triggers:
        logger.info("Triggering '%s' for GitHub PR event", trigger["name"])

        # Build message text from PR data
        message_text = (
            f"PR #{pr_data['pr_number']}: {pr_data['pr_title']}\n"
            f"URL: {pr_data['pr_url']}\n"
            f"Author: {pr_data['pr_author']}\n"
            f"Repository: {pr_data['repo_full_name']}\n"
            f"Action: {pr_data['action']}"
        )

        # Build event context for logging
        event = {"type": "github_pr", "repo_url": repo_url, **pr_data}

        # Save trigger event
        save_trigger_event_fn(trigger, event)

        # Enqueue for dispatch via ExecutionQueueService (replaces direct thread spawn)
        from .execution_queue_service import ExecutionQueueService, QueueFullError

        try:
            ExecutionQueueService.enqueue(
                trigger_id=trigger["id"],
                trigger_type="github",
                message_text=message_text,
                event_data=event,
            )
            triggered = True
        except QueueFullError:
            logger.warning(
                "Queue depth limit exceeded for trigger '%s' (%s); rejecting GitHub dispatch",
                trigger["name"],
                trigger["id"],
            )
            continue

    # --- Team dispatch ---
    from ..database import get_teams_by_trigger_source

    teams = get_teams_by_trigger_source("github")
    for team in teams:
        logger.info("Triggering team '%s' for GitHub PR event", team["name"])

        message_text = (
            f"PR #{pr_data.get('pr_number', '')}: {pr_data.get('pr_title', '')}\n"
            f"URL: {pr_data.get('pr_url', '')}\n"
            f"Author: {pr_data.get('pr_author', '')}\n"
            f"Repository: {pr_data.get('repo_full_name', '')}\n"
            f"Action: {pr_data.get('action', '')}"
        )

        event = {"type": "github_pr", "repo_url": repo_url, **pr_data}

        from .team_execution_service import TeamExecutionService

        TeamExecutionService.execute_team(team["id"], message_text, event, "github")
        triggered = True

    if not triggered:
        logger.debug("No GitHub-triggered triggers or teams found")

    return triggered


def dispatch_pr_comment_commands(
    repo_url: str,
    commands: list,
    pr_data: dict,
    save_trigger_event_fn=None,
) -> bool:
    """Dispatch PR comment slash commands to matching triggers.

    Looks up triggers with trigger_source='github' and matches them against
    the commands from the comment.  A trigger matches if:
      - Its ``detection_keyword`` is empty (matches any command), OR
      - Its ``detection_keyword`` equals one of the slash commands (e.g. '/review').

    Args:
        repo_url: The repository HTML URL.
        commands: List of slash commands found in the comment, e.g. ['/review'].
        pr_data: PR context dict (pr_number, pr_url, commenter, comment_body, …).
        save_trigger_event_fn: Optional override for saving trigger events.

    Returns:
        True if at least one trigger was dispatched.
    """
    if save_trigger_event_fn is None:
        from .execution_service import ExecutionService

        save_trigger_event_fn = ExecutionService.save_trigger_event

    triggered = False
    commands_lower = {c.lower() for c in commands}

    triggers = get_triggers_by_trigger_source("github")
    for trigger in triggers:
        kw = (trigger.get("detection_keyword") or "").strip().lower()
        # Match: no keyword (fire on any command) OR keyword is one of the commands
        if kw and kw not in commands_lower:
            continue

        matched_cmd = kw if kw else next(iter(commands_lower), "")
        logger.info("Triggering '%s' for PR comment command '%s'", trigger["name"], matched_cmd)

        message_text = (
            f"PR comment command: {matched_cmd}\n"
            f"PR #{pr_data.get('pr_number', '')}: {pr_data.get('pr_title', '')}\n"
            f"URL: {pr_data.get('pr_url', '')}\n"
            f"Commenter: {pr_data.get('commenter', '')}\n"
            f"Comment: {pr_data.get('comment_body', '')[:500]}"
        )

        event = {
            "type": "github_pr_comment",
            "repo_url": repo_url,
            "command": matched_cmd,
            **pr_data,
        }

        save_trigger_event_fn(trigger, event)

        from .execution_queue_service import ExecutionQueueService, QueueFullError

        try:
            ExecutionQueueService.enqueue(
                trigger_id=trigger["id"],
                trigger_type="github_pr_comment",
                message_text=message_text,
                event_data=event,
            )
            triggered = True
        except QueueFullError:
            logger.warning(
                "Queue full: rejecting PR comment dispatch for trigger '%s' (%s)",
                trigger["name"],
                trigger["id"],
            )

    if not triggered:
        logger.debug("No triggers matched PR comment commands: %s", commands)

    return triggered
