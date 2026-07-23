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


def _per_run_budget_tick(
    execution_id: str,
    trigger_id: str,
    entity_type: str,
    entity_id: str,
    backend_type: Optional[str],
    process: "subprocess.Popen",
    tick_state: dict,
    team_id: Optional[str] = None,
) -> None:
    """One per-run live-accounting step (Harness-1 Phase 3, P6). Fail-open:
    any error is swallowed so the monitor's period check is never disrupted.

    claude/gemini emit usage only in their terminal JSON, so extraction
    returns None mid-run and this whole tick no-ops for them (documented
    limitation); codex JSONL accumulates and works incrementally.

    Each tick re-parses the full buffered log (every 30s). Accepted for now:
    cumulative cost on very long logs — revisit with a parsed-line offset in
    tick_state if it shows up in profiles."""
    if not backend_type:
        return
    try:
        from ..db import harness_state
        from ..db.budgets import get_budget_limit
        from ..db.health_alerts import create_health_alert

        partial_log = ExecutionLogService.get_stdout_log(execution_id)
        usage = BudgetService.extract_token_usage(partial_log, backend_type)
        if not usage:
            return
        cost = BudgetService.cost_from_usage(usage, backend_type)
        harness_state.update_budget_used(execution_id, cost)
        if cost <= 0:
            return

        limit_row = get_budget_limit(entity_type, entity_id) or {}
        limit = limit_row.get("per_run_limit_usd")

        # Fix 2: also consider the team-scoped per-run limit; enforce the MIN.
        if team_id:
            team_row = get_budget_limit("team", team_id) or {}
            team_limit = team_row.get("per_run_limit_usd")
            if team_limit:
                limit = min(limit, team_limit) if limit else team_limit

        if not limit:  # NULL = off; set_budget_limit rejects <= 0, so 0.0 can't be stored
            return

        if cost >= limit:
            reason = f"per-run limit exceeded: ${cost:.2f} >= ${limit:.2f}"
            logger.warning(
                "Per-run budget limit exceeded during execution %s — terminating. %s",
                execution_id,
                reason,
            )
            # Fix 1: persist spend BEFORE the kill — run_trigger only records on exit_code==0,
            # so a SIGKILLed run's cost would otherwise be lost. Best-effort: must not block.
            try:
                usage["total_cost_usd"] = cost
                BudgetService.record_usage(
                    execution_id=execution_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    backend_type=backend_type,
                    account_id=None,
                    usage_data=usage,
                )
            except Exception as rec_err:
                logger.warning(
                    "Failed to record usage for over-budget execution %s (best-effort): %s",
                    execution_id,
                    rec_err,
                )
            try:
                import os as _os

                _os.killpg(_os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass  # already terminated
            except Exception as kill_err:
                logger.error(
                    "Failed to kill over-budget process for execution %s: %s",
                    execution_id,
                    kill_err,
                    exc_info=True,
                )
            ExecutionLogService.append_log(
                execution_id, "stderr", f"[BUDGET] Execution terminated: {reason}"
            )
            create_health_alert(
                "budget_exceeded",
                trigger_id,
                reason,
                details={"execution_id": execution_id, "per_run": True},
                severity="critical",
            )
            AuditLogService.log(
                action="execution.budget_exceeded",
                entity_type=entity_type,
                entity_id=entity_id,
                outcome="killed",
                details={"execution_id": execution_id, "reason": reason, "per_run": True},
            )
            tick_state["killed"] = True
        elif cost >= 0.8 * limit and not tick_state.get("warned"):
            tick_state["warned"] = True
            message = f"[BUDGET] approaching per-run limit: ${cost:.2f} of ${limit:.2f}"
            ExecutionLogService.append_log(execution_id, "stderr", message)
            create_health_alert(
                "budget_warning",
                trigger_id,
                message,
                details={"execution_id": execution_id, "cost": cost, "limit": limit},
                severity="warning",
            )
            AuditLogService.log(
                action="execution.budget_warning",
                entity_type=entity_type,
                entity_id=entity_id,
                outcome="warned",
                details={"execution_id": execution_id, "cost": cost, "limit": limit},
            )
    except Exception as e:  # pragma: no cover - defensive fail-open
        logger.debug("per-run budget tick failed for %s: %s", execution_id, e)


def budget_monitor(
    execution_id: str,
    trigger_id: str,
    entity_type: str,
    entity_id: str,
    process: "subprocess.Popen",
    interval_seconds: int = 30,
    backend_type: Optional[str] = None,
    team_id: Optional[str] = None,
) -> None:
    """Periodically check budget during execution and kill process if hard limit exceeded."""
    import time as _time

    start_time = _time.time()
    tick_state: dict = {"warned": False, "killed": False}

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

            # Per-run incremental accounting + ceiling (Harness-1 Phase 3, P6).
            _per_run_budget_tick(
                execution_id,
                trigger_id,
                entity_type,
                entity_id,
                backend_type,
                process,
                tick_state,
                team_id=team_id,
            )
            if tick_state.get("killed"):
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
        local_path = entry.get("local_project_path") or ""
        if entry["path_type"] == "github":
            repo_url = entry["github_repo_url"]
            logger.info("Cloning GitHub repo: %s", repo_url)
            clone_dir = GitHubService.clone_repo(repo_url)
            cloned_dirs.append(clone_dir)
            effective_paths.append(clone_dir)
            github_repo_map[clone_dir] = repo_url
        elif local_path.startswith("project://"):
            # A project ref stores only a placeholder; resolve it through the
            # workspace service, which clones from the project's github_host
            # (GHE-aware). Deliberately NOT added to cloned_dirs OR
            # github_repo_map: the workspace is persistent (or even the
            # operator's local_path checkout) — it must never be temp-dir
            # cleaned up, and never enter the auto-resolve PR flow, which
            # branch-switches, sweep-commits, and pushes whatever dir the map
            # contains.
            project_id = local_path[len("project://") :]
            try:
                from .project_workspace_service import ProjectWorkspaceService

                effective_paths.append(
                    ProjectWorkspaceService.resolve_working_directory(project_id)
                )
            except ValueError as e:
                logger.warning("Could not resolve project path %s: %s", local_path, e)
        else:
            effective_paths.append(entry["local_project_path"])
    return effective_paths


def derive_run_github_hosts(github_repo_map: dict, path_entries: list) -> set:
    """Every git host this run touches (github.com included), lowercased.

    Sources: temp-clone repo URLs (github_repo_map) + the github_host of any
    project:// path entry. Feeds the GH_HOST pin decision and the sandbox
    egress allowlist.
    """
    hosts = set()
    for repo_url in github_repo_map.values():
        try:
            _owner, _repo, host = GitHubService.parse_repo_url_with_host(repo_url)
            hosts.add(host)
        except ValueError:
            pass
    for entry in path_entries or []:
        local_path = str(entry.get("local_project_path") or "")
        if local_path.startswith("project://"):
            from ..database import get_project

            project = get_project(local_path[len("project://") :])
            if project and project.get("github_repo"):
                hosts.add((project.get("github_host") or "github.com").lower())
    return hosts


def ghe_host_to_pin(run_hosts: set) -> Optional[str]:
    """GH_HOST value to pin for a run, or None.

    Pin only when EVERY repo in the run lives on one enterprise host — gh
    treats GH_HOST as a hard remote filter, so pinning on a mixed run breaks
    every gh command inside the run's github.com clones.
    """
    if len(run_hosts) == 1:
        host = next(iter(run_hosts))
        if host != "github.com":
            return host
    return None


def gh_pin_env_additions(pin_host: str) -> dict:
    """Env additions for a run pinned to one enterprise host: GH_HOST plus the
    host's vault-stored token (if any) under the var gh reads for that host
    class — so gh/git inside the harness authenticate without the operator
    having run `gh auth login --hostname` on the server."""
    additions = {"GH_HOST": pin_host}
    try:
        from .github_credentials_service import GithubCredentialsService, gh_env_token_var

        token = GithubCredentialsService.stored_token_for_host(pin_host, accessor="execution")
        if token:
            additions[gh_env_token_var(pin_host)] = token
    except Exception as e:
        logger.warning("GitHub token lookup failed for pinned host %s: %s", pin_host, e)
    return additions


def build_subprocess_env(env_overrides: dict, proxy_url: Optional[str] = None) -> Optional[dict]:
    """Build subprocess environment, injecting vault secrets and account overrides.

    Returns a merged env dict (os.environ + overrides + vault secrets), or None if no
    overrides or secrets are present.

    Phase 24 (24-03, crit 2): when ``proxy_url`` is provided, the egress-proxy env
    (``HTTPS_PROXY``/``HTTP_PROXY``/``NO_PROXY`` via ``egress_proxy.proxy_env``) is
    merged so the child's HTTP(S) clients route through the deny-by-default egress
    proxy and match the sandbox ``--setenv``. Supplying a proxy always yields a
    concrete env (never None) so the proxy vars are actually applied.
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

    if proxy_url:
        from app.services.egress_proxy import proxy_env

        if env_overrides is None:
            env_overrides = {}
        # A lightweight handle object carries just the url that proxy_env reads.
        env_overrides.update(proxy_env(type("_H", (), {"url": proxy_url})()))

    # 4th-leak guard (REQ-41): when AGENTED_SERVER_NO_LLM_KEYS is set, strip
    # server-baked LLM inference keys from the inherited os.environ BEFORE
    # layering explicit per-request overrides (sidecar-sourced keys) on top —
    # otherwise a poison ANTHROPIC_API_KEY in the server env would pass straight
    # through here to the harness subprocess. Flag off ⇒ original behavior.
    from .. import config

    if config.server_no_llm_keys():
        base = {k: v for k, v in os.environ.items() if k not in config.LLM_INFERENCE_KEY_ENV_VARS}
        return {**base, **(env_overrides or {})}
    return {**os.environ, **env_overrides} if env_overrides else None


def fetch_pr_diff(event: dict) -> Optional[str]:
    """Fetch PR diff text from GitHub.

    Constructs the diff URL from the PR URL ({pr_url}.diff) and fetches it.
    Returns the diff text or None if unavailable.
    """
    pr_url = event.get("pr_url", "")
    if not pr_url:
        return None

    # SSRF guard (01 M7): the pr_url comes from a webhook event, so only fetch
    # from the known GitHub diff hosts over https, and cap the read size.
    import urllib.parse

    parsed = urllib.parse.urlparse(pr_url)
    allowed_hosts = {"github.com", "www.github.com"}
    ghe_host = os.environ.get("AGENTED_GITHUB_HOST")
    if ghe_host:
        allowed_hosts.add(ghe_host.lower())
    # Any GitHub Enterprise host configured on a project row is operator
    # intent — trust it the same as the env var (supports multiple GHE hosts
    # without AGENTED_GITHUB_HOST).
    try:
        from ..database import get_connection

        with get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT github_host FROM projects WHERE github_host IS NOT NULL"
            ).fetchall()
        allowed_hosts.update(str(r["github_host"]).lower() for r in rows if r["github_host"])
    except Exception as e:
        logger.debug("Could not load project github_hosts for PR-diff allowlist: %s", e)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in allowed_hosts:
        logger.warning("Refusing to fetch PR diff from untrusted URL: %s", pr_url)
        return None

    diff_url = f"{pr_url}.diff"
    max_bytes = int(os.environ.get("AGENTED_MAX_PR_DIFF_BYTES", str(10 * 1024 * 1024)))
    try:
        import urllib.request

        req = urllib.request.Request(
            diff_url,
            headers={"Accept": "text/plain", "User-Agent": "Agented/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read(max_bytes)
            return raw.decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug("Could not fetch PR diff from %s: %s", diff_url, e)
        return None


def auto_resolve_and_pr(trigger: dict, github_repo_map: dict, scan_output: str) -> List[str]:
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
