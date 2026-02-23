"""Trigger execution service with database-only status tracking and real-time logging."""

import datetime
import json
import logging
import os
import signal
import subprocess
import threading
from typing import Dict, List, Optional

from app.config import PROJECT_ROOT

from ..database import (
    PREDEFINED_TRIGGER_ID,
    get_latest_execution_for_trigger,
    get_paths_for_trigger_detailed,
    get_triggers_by_trigger_source,
    get_webhook_triggers,
)
from ..utils.json_path import get_nested_value
from .budget_service import BudgetService
from .execution_log_service import ExecutionLogService
from .github_service import GitHubService
from .process_manager import ProcessManager
from .rate_limit_service import RateLimitService

logger = logging.getLogger(__name__)

TRIGGER_LOG_DIR = os.path.join(PROJECT_ROOT, ".claude/skills/weekly-security-audit/reports")


class ExecutionService:
    """Service for trigger execution and status tracking via database."""

    # Thread-safe dict tracking rate limit detections: {execution_id: cooldown_seconds}
    _rate_limit_detected: Dict[str, int] = {}
    _rate_limit_lock = threading.Lock()

    @classmethod
    def was_rate_limited(cls, execution_id: str) -> Optional[int]:
        """Check if an execution was rate-limited. Returns cooldown seconds or None.

        Pops the entry from the tracking dict (one-time check).
        """
        if not execution_id:
            return None
        with cls._rate_limit_lock:
            return cls._rate_limit_detected.pop(execution_id, None)

    @classmethod
    def get_status(cls, trigger_id: str) -> dict:
        """Get execution status for a trigger from database."""
        execution = get_latest_execution_for_trigger(trigger_id)
        if not execution:
            return {"status": "idle"}
        return {
            "status": execution["status"],
            "started_at": execution.get("started_at"),
            "finished_at": execution.get("finished_at"),
            "error_message": execution.get("error_message"),
            "execution_id": execution["execution_id"],
        }

    @staticmethod
    def save_trigger_event(trigger: dict, event: dict) -> str:
        """Save the original trigger event for audit tracking. Returns event trigger_id."""
        os.makedirs(TRIGGER_LOG_DIR, exist_ok=True)

        trigger_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        trigger_data = {
            "trigger_id": trigger.get("id"),
            "timestamp": datetime.datetime.now().isoformat(),
            "trigger_name": trigger.get("name"),
            "trigger_source": trigger.get("trigger_source"),
            "original_event": event,
        }

        trigger_file = os.path.join(TRIGGER_LOG_DIR, f"trigger_{trigger_id}.json")
        try:
            with open(trigger_file, "w", encoding="utf-8") as f:
                json.dump(trigger_data, f, indent=2, ensure_ascii=False)
            print(f"Saved trigger event: {trigger_file}")
        except Exception as e:
            print(f"Failed to save trigger event: {e}")

        return trigger_id

    @staticmethod
    def save_threat_report(trigger_id: str, message_text: str) -> str:
        """Save webhook message as threat report file. Returns file path."""
        os.makedirs(TRIGGER_LOG_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"threat_report_{trigger_id}_{timestamp}.txt"
        filepath = os.path.join(TRIGGER_LOG_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(message_text)

        print(f"Saved threat report: {filepath}")
        return filepath

    @staticmethod
    def build_command(
        backend: str,
        prompt: str,
        allowed_paths: list = None,
        model: str = None,
        codex_settings: dict = None,
    ) -> list:
        """Build the CLI command for the specified backend."""
        if backend == "opencode":
            cmd = ["opencode", "run", "--format", "json", prompt]
            if model:
                cmd.extend(["--model", model])
            return cmd
        elif backend == "gemini":
            cmd = ["gemini", "-p", prompt, "--output-format", "json"]
            if model:
                cmd.extend(["--model", model])
            if allowed_paths:
                for path in allowed_paths:
                    cmd.extend(["--include-directories", path])
            return cmd
        elif backend == "codex":
            cmd = ["codex", "exec", "--json", "--full-auto"]
            if model:
                cmd.extend(["--model", model])
            if codex_settings:
                reasoning = codex_settings.get("reasoning_level")
                if reasoning and reasoning in ("low", "medium", "high"):
                    cmd.extend(["--reasoning-effort", reasoning])
            cmd.append(prompt)
            return cmd
        else:
            # claude (default)
            cmd = [
                "claude",
                "-p",
                prompt,
                "--verbose",
                "--output-format",
                "json",
                "--allowedTools",
                "Read,Glob,Grep,Bash",
            ]
            if model:
                cmd.extend(["--model", model])
            if allowed_paths:
                for path in allowed_paths:
                    cmd.extend(["--add-dir", path])
            return cmd

    @classmethod
    def _stream_pipe(cls, execution_id: str, stream_name: str, pipe, backend_type: str = None):
        """Read from a pipe line by line and stream to log service.

        When stream_name is 'stderr' and backend_type is provided, checks each line
        for rate limit patterns and flags the execution if detected.
        """
        try:
            for line in iter(pipe.readline, ""):
                if line:
                    content = line.rstrip("\n\r")
                    ExecutionLogService.append_log(execution_id, stream_name, content)
                    print(f"[{stream_name}] {content}")

                    # Check for rate limit patterns in stderr
                    if stream_name == "stderr" and backend_type:
                        cooldown = RateLimitService.check_stderr_line(content, backend_type)
                        if cooldown is not None:
                            with cls._rate_limit_lock:
                                cls._rate_limit_detected[execution_id] = cooldown
                            print(
                                f"[rate-limit] Detected for execution {execution_id}, "
                                f"cooldown={cooldown}s"
                            )
        except Exception as e:
            print(f"Error reading {stream_name}: {e}")
        finally:
            pipe.close()

    @classmethod
    def run_trigger(
        cls,
        trigger: dict,
        message_text: str,
        event: dict = None,
        trigger_type: str = "webhook",
        env_overrides: dict = None,
        account_id: int = None,
        working_directory: str = None,
    ) -> Optional[str]:
        """Execute a trigger's prompt with real-time log streaming. Returns execution_id."""
        trigger_id = trigger["id"]
        execution_id = None
        cloned_dirs = []  # temp dirs to clean up
        github_repo_map = {}  # clone_dir -> repo_url (for auto-resolve PR flow)

        try:
            # Get detailed path info (includes path_type and github_repo_url)
            path_entries = get_paths_for_trigger_detailed(trigger_id)

            effective_paths = []
            for entry in path_entries:
                if entry["path_type"] == "github":
                    repo_url = entry["github_repo_url"]
                    print(f"Cloning GitHub repo: {repo_url}")
                    clone_dir = GitHubService.clone_repo(repo_url)
                    cloned_dirs.append(clone_dir)
                    effective_paths.append(clone_dir)
                    github_repo_map[clone_dir] = repo_url
                else:
                    effective_paths.append(entry["local_project_path"])

            paths_str = ", ".join(effective_paths) if effective_paths else "no paths configured"

            # Build prompt from template
            prompt = trigger["prompt_template"]
            prompt = prompt.replace("{trigger_id}", trigger_id)
            prompt = prompt.replace("{bot_id}", trigger_id)  # Legacy placeholder support
            prompt = prompt.replace("{paths}", paths_str)
            prompt = prompt.replace("{message}", message_text)

            # Add trigger context if available
            if event:
                # Handle GitHub PR placeholders
                if event.get("type") == "github_pr":
                    prompt = prompt.replace("{pr_url}", event.get("pr_url", ""))
                    prompt = prompt.replace("{pr_number}", str(event.get("pr_number", "")))
                    prompt = prompt.replace("{pr_title}", event.get("pr_title", ""))
                    prompt = prompt.replace("{pr_author}", event.get("pr_author", ""))
                    prompt = prompt.replace("{repo_url}", event.get("repo_url", ""))
                    prompt = prompt.replace("{repo_full_name}", event.get("repo_full_name", ""))

            # Prepend skill_command if configured and not already in prompt
            skill_command = trigger.get("skill_command", "")
            if skill_command and not prompt.lstrip().startswith(skill_command):
                prompt = f"{skill_command} {prompt}"

            # For security audit skill, save message as threat report and prepend path
            if "/weekly-security-audit" in prompt:
                threat_report_path = cls.save_threat_report(trigger_id, message_text)
                prompt = prompt.replace(
                    "/weekly-security-audit", f"/weekly-security-audit {threat_report_path}"
                )

            backend = trigger["backend_type"]
            model = trigger.get("model")
            cmd = cls.build_command(backend, prompt, effective_paths, model)

            # Wrap with stdbuf to force line-buffered output for real-time streaming
            # -oL = line buffer stdout, -eL = line buffer stderr
            cmd = ["stdbuf", "-oL", "-eL"] + cmd

            cmd_str = " ".join(cmd)

            effective_cwd = working_directory or PROJECT_ROOT
            print(f"Executing trigger '{trigger['name']}': {cmd_str[:200]}...")
            print(f"Working directory: {effective_cwd}")

            # Snapshot trigger config for audit trail
            trigger_config_snapshot = json.dumps(trigger, default=str)

            # Start execution logging
            execution_id = ExecutionLogService.start_execution(
                trigger_id=trigger_id,
                trigger_type=trigger_type,
                prompt=prompt,
                backend_type=backend,
                command=cmd_str,
                trigger_config_snapshot=trigger_config_snapshot,
                account_id=account_id,
            )

            # Pre-execution budget check (wrapped in try/except -- never crash execution flow)
            try:
                budget_check = BudgetService.check_budget("trigger", trigger_id)
                if not budget_check["allowed"]:
                    logger.warning(
                        f"Budget check blocked execution for trigger "
                        f"'{trigger.get('name', trigger_id)}': "
                        f"{budget_check.get('reason', 'unknown')}"
                    )
                    ExecutionLogService.finish_execution(
                        execution_id=execution_id,
                        status="failed",
                        exit_code=-1,
                        error_message=f"Budget limit exceeded: "
                        f"{budget_check.get('reason', 'hard limit reached')}",
                    )
                    return execution_id
            except Exception as e:
                logger.error(
                    f"Budget pre-check failed for trigger '{trigger.get('name', trigger_id)}': {e}"
                )

            # Build process environment with optional overrides
            proc_env = {**os.environ, **env_overrides} if env_overrides else None

            # Use Popen for streaming output (start_new_session for process group management)
            process = subprocess.Popen(
                cmd,
                cwd=effective_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                start_new_session=True,  # Process group for clean cleanup
                env=proc_env,
            )

            # Register with ProcessManager for cancellation and shutdown tracking
            ProcessManager.register(execution_id, process, trigger_id)

            # Start threads to read stdout and stderr
            stdout_thread = threading.Thread(
                target=cls._stream_pipe, args=(execution_id, "stdout", process.stdout), daemon=True
            )
            stderr_thread = threading.Thread(
                target=cls._stream_pipe,
                args=(execution_id, "stderr", process.stderr, backend),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            # Wait for process with timeout
            try:
                exit_code = process.wait(timeout=600)  # 10 minute timeout
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError as e:
                    logger.debug("Process already exited during timeout cleanup: %s", e)
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)
                print(f"Trigger '{trigger['name']}' timed out")
                ExecutionLogService.finish_execution(
                    execution_id=execution_id,
                    status="timeout",
                    error_message="Command timed out after 10 minutes",
                )
                return execution_id

            # Wait for pipe readers to finish
            stdout_thread.join(timeout=10)
            stderr_thread.join(timeout=10)

            print(f"{backend} exit code: {exit_code}")

            # Check if this execution was cancelled via the cancel endpoint
            if ProcessManager.is_cancelled(execution_id):
                ExecutionLogService.finish_execution(
                    execution_id=execution_id,
                    status="cancelled",
                    exit_code=exit_code,
                    error_message="Cancelled by user",
                )
            elif exit_code == 0:
                # Auto-resolve + PR flow for security trigger with GitHub repos
                if (
                    trigger.get("auto_resolve")
                    and trigger_id == PREDEFINED_TRIGGER_ID
                    and github_repo_map
                ):
                    # Get scan output from execution logs
                    scan_output = ExecutionLogService.get_stdout_log(execution_id)
                    cls._auto_resolve_and_pr(trigger, github_repo_map, scan_output)
                ExecutionLogService.finish_execution(
                    execution_id=execution_id, status="success", exit_code=exit_code
                )

                # Extract and record token usage after successful execution
                try:
                    stdout_log = ExecutionLogService.get_stdout_log(execution_id)
                    usage_data = BudgetService.extract_token_usage(stdout_log, backend)
                    if usage_data:
                        entity_type = trigger.get("_entity_type", "trigger")
                        entity_id = trigger.get("_entity_id", trigger_id)
                        BudgetService.record_usage(
                            execution_id=execution_id,
                            entity_type=entity_type,
                            entity_id=entity_id,
                            backend_type=backend,
                            account_id=account_id,
                            usage_data=usage_data,
                        )
                except Exception as e:
                    print(f"Failed to record token usage for {execution_id}: {e}")
            else:
                error_msg = f"Exit code: {exit_code}"
                ExecutionLogService.finish_execution(
                    execution_id=execution_id,
                    status="failed",
                    exit_code=exit_code,
                    error_message=error_msg,
                )

        except FileNotFoundError:
            backend = trigger.get("backend_type", "claude")
            error_msg = f"{backend} command not found"
            print(f"{error_msg}. Is {backend} CLI installed?")
            if execution_id:
                ExecutionLogService.finish_execution(
                    execution_id=execution_id, status="failed", error_message=error_msg
                )
        except Exception as e:
            error_msg = str(e)
            print(f"Error running trigger '{trigger['name']}': {error_msg}")
            if execution_id:
                ExecutionLogService.finish_execution(
                    execution_id=execution_id, status="failed", error_message=error_msg
                )
        finally:
            # Clean up all cloned directories
            for d in cloned_dirs:
                GitHubService.cleanup_clone(d)
            # Remove from ProcessManager tracking
            if execution_id:
                ProcessManager.cleanup(execution_id)

        return execution_id

    @classmethod
    def _auto_resolve_and_pr(
        cls, trigger: dict, github_repo_map: dict, scan_output: str
    ) -> List[str]:
        """Resolve issues in GitHub repos and create PRs. Returns list of PR URLs."""
        pr_urls = []

        for clone_dir, repo_url in github_repo_map.items():
            try:
                branch_name = GitHubService.generate_branch_name()

                # Create a new branch
                if not GitHubService.create_branch(clone_dir, branch_name):
                    print(f"Skipping PR for {repo_url}: branch creation failed")
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
                print(f"Running resolve on {repo_url}...")
                subprocess.run(
                    cmd,
                    cwd=clone_dir,
                    capture_output=True,
                    text=True,
                    timeout=900,  # 15 minute timeout
                    start_new_session=True,  # Process group for clean cleanup
                )

                # Commit changes
                committed = GitHubService.commit_changes(
                    clone_dir,
                    "fix(security): resolve vulnerabilities\n\n" "Automatic security fix by Agented",
                )

                if committed:
                    if GitHubService.push_branch(clone_dir, branch_name):
                        pr_url = GitHubService.create_pull_request(
                            repo_path=clone_dir,
                            branch_name=branch_name,
                            title="fix(security): resolve vulnerabilities",
                            body=(
                                "## Security Fix\n\n"
                                "This PR was automatically generated by Agented"
                                "to resolve detected security vulnerabilities.\n\n"
                                "Please review the changes carefully before merging."
                            ),
                        )
                        if pr_url:
                            pr_urls.append(pr_url)
                else:
                    print(f"No changes to resolve for {repo_url}")

            except Exception as e:
                print(f"Auto-resolve failed for {repo_url}: {e}")

        return pr_urls

    @classmethod
    def dispatch_webhook_event(cls, payload: dict) -> bool:
        """Dispatch a webhook event to matching triggers and teams based on configurable field matching.

        Args:
            payload: The JSON webhook payload

        Returns:
            True if at least one trigger or team was triggered
        """
        triggered = False

        # --- Trigger dispatch ---
        triggers = get_webhook_triggers()
        for trigger in triggers:
            match_field_path = trigger.get("match_field_path")
            match_field_value = trigger.get("match_field_value")
            text_field_path = trigger.get("text_field_path", "text")
            detection_keyword = trigger.get("detection_keyword", "")

            # Check if payload matches the trigger's field criteria
            if match_field_path and match_field_value:
                actual_value = get_nested_value(payload, match_field_path)
                if str(actual_value) != str(match_field_value):
                    continue  # Field value doesn't match

            # Extract text from payload using configured path
            text = get_nested_value(payload, text_field_path)
            if text is None:
                text = ""
            elif not isinstance(text, str):
                text = str(text)

            # Check keyword match if detection_keyword is set
            if detection_keyword and detection_keyword not in text:
                continue  # Keyword not found in text

            print(f"Trigger '{trigger['name']}' triggered by webhook")
            cls.save_trigger_event(trigger, payload)

            # Delegate to team execution if execution_mode is 'team'
            if trigger.get("execution_mode") == "team" and trigger.get("team_id"):
                from .team_execution_service import TeamExecutionService

                thread = threading.Thread(
                    target=TeamExecutionService.execute_team,
                    args=(trigger["team_id"], text, payload, "webhook"),
                    daemon=True,
                )
                thread.start()
                triggered = True
                continue  # Skip normal dispatch for this trigger

            from .orchestration_service import OrchestrationService

            thread = threading.Thread(
                target=OrchestrationService.execute_with_fallback,
                args=(trigger, text, payload, "webhook"),
                daemon=True,
            )
            thread.start()
            triggered = True

        # --- Team dispatch ---
        from ..database import get_webhook_teams

        teams = get_webhook_teams()
        for team in teams:
            # Parse trigger_config for field-matching rules (same schema as triggers)
            trigger_config = team.get("trigger_config")
            if trigger_config and isinstance(trigger_config, str):
                try:
                    trigger_config = json.loads(trigger_config)
                except (json.JSONDecodeError, TypeError):
                    trigger_config = {}
            if not trigger_config:
                trigger_config = {}

            match_field_path = trigger_config.get("match_field_path")
            match_field_value = trigger_config.get("match_field_value")
            text_field_path = trigger_config.get("text_field_path", "text")
            detection_keyword = trigger_config.get("detection_keyword", "")

            # Check if payload matches the team's field criteria
            if match_field_path and match_field_value:
                actual_value = get_nested_value(payload, match_field_path)
                if str(actual_value) != str(match_field_value):
                    continue

            # Extract text from payload
            text = get_nested_value(payload, text_field_path)
            if text is None:
                text = ""
            elif not isinstance(text, str):
                text = str(text)

            # Check keyword match
            if detection_keyword and detection_keyword not in text:
                continue

            print(f"Team '{team['name']}' triggered by webhook")

            from .team_execution_service import TeamExecutionService

            TeamExecutionService.execute_team(team["id"], text, payload, "webhook")
            triggered = True

        if not triggered:
            print("No webhook-triggered triggers or teams matched")

        return triggered

    @staticmethod
    def build_resolve_command(audit_summary: str, project_paths: list) -> list:
        """Build Claude command with edit permissions for resolving security issues."""
        prompt = f"Resolve security threats reported by these results. Update dependencies and fix vulnerabilities:\n\n{audit_summary}"
        cmd = [
            "claude",
            "-p",
            prompt,
            "--verbose",
            "--allowedTools",
            "Read,Glob,Grep,Bash,Edit,Write",
        ]
        for path in project_paths:
            cmd.extend(["--add-dir", path])
        return cmd

    @classmethod
    def run_resolve_command(cls, audit_summary: str, project_paths: list):
        """Execute Claude command to resolve security issues."""
        cmd = cls.build_resolve_command(audit_summary, project_paths)

        try:
            print(f"Executing resolve command: {' '.join(cmd[:10])}...")
            print(f"Working directory: {PROJECT_ROOT}")
            print(f"Project paths: {project_paths}")
            result = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=900,  # 15 minute timeout
            )
            print(f"Resolve output (stdout): {result.stdout}")
            if result.stderr:
                print(f"Resolve output (stderr): {result.stderr}")
            print(f"Resolve exit code: {result.returncode}")
        except subprocess.TimeoutExpired:
            print("Resolve command timed out after 15 minutes")
        except FileNotFoundError:
            print("Claude command not found. Is Claude CLI installed?")
        except Exception as e:
            print(f"Error running resolve command: {e}")

    @classmethod
    def dispatch_github_event(cls, repo_url: str, pr_data: dict) -> bool:
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

        Returns:
            True if at least one trigger or team was triggered
        """
        triggered = False

        # --- Trigger dispatch ---
        triggers = get_triggers_by_trigger_source("github")
        for trigger in triggers:
            print(f"Triggering '{trigger['name']}' for GitHub PR event")

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
            cls.save_trigger_event(trigger, event)

            # Delegate to team execution if execution_mode is 'team'
            if trigger.get("execution_mode") == "team" and trigger.get("team_id"):
                from .team_execution_service import TeamExecutionService

                thread = threading.Thread(
                    target=TeamExecutionService.execute_team,
                    args=(trigger["team_id"], message_text, event, "github_webhook"),
                    daemon=True,
                )
                thread.start()
                triggered = True
                continue  # Skip normal dispatch for this trigger

            # Run trigger in background thread via orchestration (handles fallback chains)
            from .orchestration_service import OrchestrationService

            thread = threading.Thread(
                target=OrchestrationService.execute_with_fallback,
                args=(trigger, message_text, event, "github_webhook"),
                daemon=True,
            )
            thread.start()
            triggered = True

        # --- Team dispatch ---
        from ..database import get_teams_by_trigger_source

        teams = get_teams_by_trigger_source("github")
        for team in teams:
            print(f"Triggering team '{team['name']}' for GitHub PR event")

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
            print("No GitHub-triggered triggers or teams found")

        return triggered

