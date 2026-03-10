"""Core execution running helpers extracted from ExecutionService.

Contains subprocess management, pipe streaming, budget monitoring,
repo cloning, environment building, PR diff fetching, and auto-resolve logic.
"""

import logging
import os
import signal
import subprocess
import threading
from typing import Dict, List, Optional

from app.config import PROJECT_ROOT

from ..database import PREDEFINED_TRIGGER_ID
from ..db.health_alerts import create_health_alert
from .audit_log_service import AuditLogService
from .budget_service import BudgetService
from .execution_log_service import ExecutionLogService
from .github_service import GitHubService
from .process_manager import ProcessManager
from .rate_limit_service import RateLimitService

logger = logging.getLogger(__name__)


def stream_pipe(
    execution_id: str,
    stream_name: str,
    pipe,
    backend_type: str = None,
    rate_limit_detected: Dict[str, int] = None,
    transient_failure_detected: Dict[str, str] = None,
    lock: threading.Lock = None,
) -> None:
    """Read from a pipe line by line and stream to log service.

    When stream_name is 'stderr' and backend_type is provided, checks each line
    for rate limit patterns and flags the execution if detected.

    Args:
        execution_id: The execution trace ID
        stream_name: 'stdout' or 'stderr'
        pipe: The subprocess pipe to read from
        backend_type: Backend type for rate-limit detection (only checked on stderr)
        rate_limit_detected: Shared dict to record rate-limit detections
        transient_failure_detected: Shared dict to record transient failure detections
        lock: Threading lock guarding the shared dicts
    """
    try:
        for line in iter(pipe.readline, ""):
            if line:
                content = line.rstrip("\n\r")
                ExecutionLogService.append_log(execution_id, stream_name, content)
                logger.debug("[%s] %s", stream_name, content)

                # Check for rate limit patterns in stderr
                if stream_name == "stderr" and backend_type:
                    cooldown = RateLimitService.check_stderr_line(content, backend_type)
                    if cooldown is not None:
                        if lock and rate_limit_detected is not None:
                            with lock:
                                rate_limit_detected[execution_id] = cooldown
                        logger.warning(
                            "Rate limit detected for execution %s, cooldown=%ds",
                            execution_id,
                            cooldown,
                        )
                        AuditLogService.log(
                            action="rate_limit.detected",
                            entity_type="execution",
                            entity_id=execution_id,
                            outcome="rate_limited",
                            details={
                                "backend_type": backend_type,
                                "cooldown_seconds": cooldown,
                            },
                        )
                    else:
                        # Check for transient failure patterns (502/503/timeout/connection)
                        from .circuit_breaker_service import CircuitBreakerService

                        if CircuitBreakerService.is_transient_error(error=content):
                            if lock and transient_failure_detected is not None:
                                with lock:
                                    # Only record first transient error per execution
                                    if execution_id not in transient_failure_detected:
                                        transient_failure_detected[execution_id] = content
                                        logger.warning(
                                            "Transient failure detected for execution %s: %s",
                                            execution_id,
                                            content[:200],
                                        )
    except (OSError, ValueError) as e:
        logger.error(
            "Error reading %s stream for execution %s: %s",
            stream_name,
            execution_id,
            e,
            exc_info=True,
        )
    except Exception:
        logger.exception(
            "Unexpected error reading %s stream for execution %s", stream_name, execution_id
        )
    finally:
        pipe.close()


def budget_monitor(
    execution_id: str,
    trigger_id: str,
    entity_type: str,
    entity_id: str,
    process: "subprocess.Popen",
    interval_seconds: int = 30,
) -> None:
    """Periodically check budget during execution and kill process if hard limit exceeded."""
    import time as _time

    start_time = _time.time()

    while process.poll() is None:
        _time.sleep(interval_seconds)
        if process.poll() is not None:
            break
        try:
            # Check cost budget
            budget_check = BudgetService.check_budget(entity_type, entity_id)
            if not budget_check["allowed"]:
                reason = budget_check.get("reason", "hard limit reached")
                logger.warning(
                    "Budget hard limit exceeded during execution %s (%s/%s) — terminating process. %s",
                    execution_id,
                    entity_type,
                    entity_id,
                    reason,
                )
                try:
                    import os as _os

                    _os.killpg(_os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Intentionally silenced: process already terminated
                except Exception as kill_err:
                    logger.error(
                        "Failed to kill over-budget process for execution %s: %s",
                        execution_id,
                        kill_err,
                        exc_info=True,
                    )
                ExecutionLogService.append_log(
                    execution_id,
                    "stderr",
                    f"[BUDGET] Execution terminated: {reason}",
                )
                AuditLogService.log(
                    action="execution.budget_exceeded",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    outcome="killed",
                    details={"execution_id": execution_id, "reason": reason},
                )
                break

            # Check execution time limit
            elapsed = _time.time() - start_time
            if BudgetService.check_execution_time_limit(entity_type, entity_id, elapsed):
                from ..db.budgets import get_budget_limit

                limits = get_budget_limit(entity_type, entity_id)
                limit_seconds = limits.get("max_execution_time_seconds") if limits else None
                logger.warning(
                    "Execution time limit exceeded (%ds > %ds) for execution %s — "
                    "terminating via cancel_graceful",
                    int(elapsed),
                    limit_seconds,
                    execution_id,
                )
                ProcessManager.cancel_graceful(execution_id)
                ExecutionLogService.append_log(
                    execution_id,
                    "stderr",
                    f"[BUDGET] Execution cancelled: time limit exceeded "
                    f"({int(elapsed)}s > {limit_seconds}s)",
                )
                AuditLogService.log(
                    action="execution.budget_exceeded",
                    entity_type=entity_type,
                    entity_id=entity_id,
                    outcome="killed",
                    details={
                        "execution_id": execution_id,
                        "reason": "execution_time_limit_exceeded",
                        "elapsed_seconds": int(elapsed),
                        "limit_seconds": limit_seconds,
                    },
                )
                create_health_alert(
                    alert_type="budget_exceeded",
                    trigger_id=trigger_id,
                    message=(
                        f"Execution cancelled: time limit exceeded "
                        f"({int(elapsed)}s > {limit_seconds}s)"
                    ),
                    details={
                        "execution_id": execution_id,
                        "elapsed_seconds": int(elapsed),
                        "limit_seconds": limit_seconds,
                    },
                    severity="critical",
                )
                break
        except Exception as monitor_err:
            logger.debug("Budget monitor check failed for %s: %s", execution_id, monitor_err)


def clone_repos(path_entries: list, cloned_dirs: list, github_repo_map: dict) -> list:
    """Resolve path entries into effective local paths, cloning GitHub repos as needed.

    Mutates cloned_dirs (appends temp dirs) and github_repo_map (clone_dir -> repo_url).
    Returns effective_paths list.
    """
    effective_paths = []
    for entry in path_entries:
        if entry["path_type"] == "github":
            repo_url = entry["github_repo_url"]
            logger.info("Cloning GitHub repo: %s", repo_url)
            clone_dir = GitHubService.clone_repo(repo_url)
            cloned_dirs.append(clone_dir)
            effective_paths.append(clone_dir)
            github_repo_map[clone_dir] = repo_url
        else:
            effective_paths.append(entry["local_project_path"])
    return effective_paths


def build_subprocess_env(env_overrides: dict) -> Optional[dict]:
    """Build subprocess environment, injecting vault secrets and account overrides.

    Returns a merged env dict (os.environ + overrides + vault secrets), or None if no
    overrides or secrets are present.
    """
    # Inject secrets from vault into subprocess environment
    try:
        from app.services.secret_vault_service import SecretVaultService

        if SecretVaultService.is_configured():
            vault_secrets = SecretVaultService.get_secrets_for_execution(scope="global")
            if vault_secrets:
                if env_overrides is None:
                    env_overrides = {}
                env_overrides.update(vault_secrets)
    except Exception as e:
        logger.warning("Failed to inject vault secrets into execution env: %s", e)

    return {**os.environ, **env_overrides} if env_overrides else None


def fetch_pr_diff(event: dict) -> Optional[str]:
    """Fetch PR diff text from GitHub.

    Constructs the diff URL from the PR URL ({pr_url}.diff) and fetches it.
    Returns the diff text or None if unavailable.
    """
    pr_url = event.get("pr_url", "")
    if not pr_url:
        return None

    diff_url = f"{pr_url}.diff"
    try:
        import urllib.request

        req = urllib.request.Request(
            diff_url,
            headers={"Accept": "text/plain", "User-Agent": "Agented/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug("Could not fetch PR diff from %s: %s", diff_url, e)
        return None


def auto_resolve_and_pr(
    trigger: dict, github_repo_map: dict, scan_output: str
) -> List[str]:
    """Resolve issues in GitHub repos and create PRs. Returns list of PR URLs."""
    pr_urls = []

    for clone_dir, repo_url in github_repo_map.items():
        try:
            branch_name = GitHubService.generate_branch_name()

            # Create a new branch
            if not GitHubService.create_branch(clone_dir, branch_name):
                logger.warning("Skipping PR for %s: branch creation failed", repo_url)
                continue

            # Run resolve command with Edit/Write permissions
            resolve_prompt = (
                "IMPORTANT: You must ONLY fix the specific security vulnerabilities "
                "listed in the audit results below. Do NOT make any other changes "
                "or general security improvements.\n\n"
                "## Audit Results\n\n"
                f"{scan_output}\n\n"
                "## Instructions\n"
                "1. Read the audit findings above carefully\n"
                "2. For each vulnerability found, apply the specific fix\n"
                "3. If a fix command is provided (like 'pip install package>=version'), execute it\n"
                "4. Do NOT modify any code that isn't directly related to the vulnerabilities listed\n"
                "5. If no vulnerabilities were found in the audit, make NO changes\n"
            )
            cmd = [
                "claude",
                "-p",
                resolve_prompt,
                "--verbose",
                "--allowedTools",
                "Read,Glob,Grep,Bash,Edit,Write",
                "--add-dir",
                clone_dir,
            ]
            logger.info("Running resolve on %s...", repo_url)
            resolve_result = subprocess.run(
                cmd,
                cwd=clone_dir,
                capture_output=True,
                text=True,
                timeout=900,  # 15 minute timeout
                start_new_session=True,  # Process group for clean cleanup
            )
            if resolve_result.returncode != 0:
                logger.warning(
                    "Auto-resolve command failed for %s (exit=%d): %s",
                    repo_url,
                    resolve_result.returncode,
                    resolve_result.stderr[:500] if resolve_result.stderr else "(no stderr)",
                )
                continue

            # Commit changes
            committed = GitHubService.commit_changes(
                clone_dir,
                "fix(security): resolve vulnerabilities\n\nAutomatic security fix by Agented",
            )

            if committed:
                pushed = GitHubService.push_branch(clone_dir, branch_name)
                if pushed:
                    pr_url = GitHubService.create_pull_request(
                        repo_path=clone_dir,
                        branch_name=branch_name,
                        title="fix(security): resolve vulnerabilities",
                        body=(
                            "## Security Fix\n\n"
                            "This PR was automatically generated by Agented "
                            "to resolve detected security vulnerabilities.\n\n"
                            "Please review the changes carefully before merging."
                        ),
                    )
                    if pr_url:
                        pr_urls.append(pr_url)
                    else:
                        # PR creation failed after branch was pushed — roll back the remote branch
                        logger.warning(
                            "PR creation failed for %s; rolling back remote branch '%s'",
                            repo_url,
                            branch_name,
                        )
                        GitHubService.delete_remote_branch(clone_dir, branch_name)
            else:
                logger.info("No changes to resolve for %s", repo_url)

        except Exception:
            logger.exception("Auto-resolve failed for %s", repo_url)

    return pr_urls
