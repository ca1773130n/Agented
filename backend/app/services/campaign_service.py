"""Campaign service for multi-repo orchestration.

Executes a single trigger across multiple repositories simultaneously,
with semaphore-limited concurrency (max 5 concurrent repo executions).
"""

import logging
import threading
from typing import Optional

from ..db.campaigns import (
    add_campaign_execution,
    create_campaign,
    get_campaign,
    list_campaign_executions,
    update_campaign_execution,
    update_campaign_status,
)

logger = logging.getLogger(__name__)

# Maximum concurrent repo executions across all campaigns.
# Per 11-RESEARCH.md Pitfall 5: semaphore prevents resource exhaustion.
_semaphore = threading.Semaphore(5)


def start_campaign(name: str, trigger_id: str, repo_urls: list[str]) -> Optional[str]:
    """Start a multi-repo campaign.

    Creates campaign record, spawns per-repo execution threads, and returns
    the campaign_id immediately (non-blocking).
    """
    campaign_id = create_campaign(name, trigger_id, repo_urls)
    if not campaign_id:
        return None

    # Create execution entries for each repo
    for repo_url in repo_urls:
        add_campaign_execution(campaign_id, repo_url)

    # Spawn a thread per repo
    threads = []
    for repo_url in repo_urls:
        t = threading.Thread(
            target=_execute_repo,
            args=(campaign_id, trigger_id, repo_url),
            daemon=True,
            name=f"campaign-{campaign_id}-{repo_url}",
        )
        threads.append(t)
        t.start()

    # Monitor thread waits for all repo threads to complete
    monitor = threading.Thread(
        target=_monitor_campaign,
        args=(campaign_id, threads),
        daemon=True,
        name=f"campaign-monitor-{campaign_id}",
    )
    monitor.start()

    return campaign_id


def _execute_repo(campaign_id: str, trigger_id: str, repo_url: str):
    """Execute a single repo within a campaign. Acquires semaphore for concurrency control."""
    acquired = False
    try:
        _semaphore.acquire()
        acquired = True

        update_campaign_execution(campaign_id, repo_url, status="running")

        # Deferred import to avoid circular imports
        from ..db.triggers import get_trigger
        from .orchestration_service import OrchestrationService

        trigger = get_trigger(trigger_id)
        if not trigger:
            update_campaign_execution(
                campaign_id,
                repo_url,
                status="failed",
                error=f"Trigger {trigger_id} not found",
            )
            return

        # Execute with fallback using the trigger and repo URL as context
        result = OrchestrationService.execute_with_fallback(
            trigger=trigger,
            message_text=f"Campaign execution for {repo_url}",
            event={"repo_url": repo_url, "campaign_id": campaign_id},
            trigger_type=trigger.get("trigger_source", "webhook"),
        )

        if result.execution_id:
            update_campaign_execution(
                campaign_id,
                repo_url,
                execution_id=result.execution_id,
                status="completed",
            )
        else:
            update_campaign_execution(
                campaign_id,
                repo_url,
                status="failed",
                error=f"Execution not dispatched: {result.status.value} - {result.detail or ''}",
            )

    except Exception as e:
        logger.error("Campaign %s repo %s failed: %s", campaign_id, repo_url, e)
        update_campaign_execution(
            campaign_id,
            repo_url,
            status="failed",
            error=str(e),
        )
    finally:
        if acquired:
            _semaphore.release()


def _monitor_campaign(campaign_id: str, threads: list):
    """Wait for all repo threads to complete, then update campaign status."""
    for t in threads:
        t.join()

    # Count completed/failed
    executions = list_campaign_executions(campaign_id)
    completed = sum(1 for e in executions if e["status"] == "completed")
    failed = sum(1 for e in executions if e["status"] == "failed")

    if failed == 0:
        status = "completed"
    elif completed == 0:
        status = "failed"
    else:
        status = "partial_failure"

    update_campaign_status(campaign_id, status, completed=completed, failed=failed)

    # Post-completion notification (non-blocking, deferred import)
    try:
        from .notification_service import NotificationService

        NotificationService.on_execution_complete(
            execution_id=campaign_id,
            trigger_id=None,
            status=status,
            duration_ms=None,
        )
    except ImportError:
        logger.debug("NotificationService not available, skipping campaign notification")
    except Exception as e:
        logger.warning("Campaign notification failed: %s", e)

    logger.info(
        "Campaign %s finished: status=%s completed=%d failed=%d",
        campaign_id,
        status,
        completed,
        failed,
    )


def get_campaign_results(campaign_id: str) -> Optional[dict]:
    """Get consolidated campaign results grouped by repo."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return None

    executions = list_campaign_executions(campaign_id)
    repos = {}
    for ex in executions:
        repos[ex["repo_url"]] = {
            "status": ex["status"],
            "execution_id": ex.get("execution_id"),
            "started_at": ex.get("started_at"),
            "finished_at": ex.get("finished_at"),
            "error_message": ex.get("error_message"),
        }

    return {
        "campaign": campaign,
        "repos": repos,
        "summary": {
            "total": campaign["total_repos"],
            "completed": campaign["completed_repos"],
            "failed": campaign["failed_repos"],
        },
    }
