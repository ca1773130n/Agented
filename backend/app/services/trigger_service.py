"""Trigger management service."""

from http import HTTPStatus
from pathlib import Path
from typing import Tuple

from ..database import (
    PREDEFINED_TRIGGER_ID,
    add_github_repo,
    add_project_path,
    add_project_to_trigger,
    add_trigger,
    delete_trigger,
    get_all_triggers,
    get_project,
    get_trigger,
    list_paths_for_trigger,
    remove_github_repo,
    remove_project_from_trigger,
    remove_project_path,
    update_trigger,
    update_trigger_auto_resolve,
)
from .execution_service import ExecutionService
from .github_service import GitHubService
from .scheduler_service import SchedulerService


class TriggerService:
    """Service for trigger CRUD operations."""

    @staticmethod
    def list_triggers() -> Tuple[dict, HTTPStatus]:
        """Get all triggers with path counts and execution status."""
        triggers = get_all_triggers()
        # Add execution status to each trigger
        for trigger in triggers:
            trigger["execution_status"] = ExecutionService.get_status(trigger["id"])
        return {"triggers": triggers}, HTTPStatus.OK

    @staticmethod
    def get_trigger_detail(trigger_id: str) -> Tuple[dict, HTTPStatus]:
        """Get a single trigger with paths."""
        trigger = get_trigger(trigger_id)
        if not trigger:
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

        trigger["paths"] = list_paths_for_trigger(trigger_id)
        trigger["execution_status"] = ExecutionService.get_status(trigger_id)
        return trigger, HTTPStatus.OK

    @staticmethod
    def create_trigger(data: dict) -> Tuple[dict, HTTPStatus]:
        """Create a new trigger."""
        name = data.get("name")
        prompt_template = data.get("prompt_template")
        backend_type = data.get("backend_type", "claude")
        trigger_source = data.get("trigger_source", "webhook")

        # Webhook matching fields
        match_field_path = data.get("match_field_path")
        match_field_value = data.get("match_field_value")
        text_field_path = data.get("text_field_path", "text")
        detection_keyword = data.get("detection_keyword", "")

        # Deprecated field for backward compatibility
        group_id = data.get("group_id", 0)

        if not name or not prompt_template:
            return {"error": "name and prompt_template required"}, HTTPStatus.BAD_REQUEST

        # For webhook trigger, validate that match_field_path and match_field_value are provided together
        if trigger_source == "webhook":
            if bool(match_field_path) != bool(match_field_value):
                return {
                    "error": "Both match_field_path and match_field_value must be provided together"
                }, HTTPStatus.BAD_REQUEST

        try:
            group_id = int(group_id) if group_id is not None else 0
        except (ValueError, TypeError):
            return {"error": "group_id must be a number"}, HTTPStatus.BAD_REQUEST

        if backend_type not in ("claude", "opencode"):
            return {"error": "backend_type must be 'claude' or 'opencode'"}, HTTPStatus.BAD_REQUEST

        if trigger_source not in ("webhook", "github", "manual", "scheduled"):
            return {
                "error": "trigger_source must be 'webhook', 'github', 'manual', or 'scheduled'"
            }, HTTPStatus.BAD_REQUEST

        # Extract schedule configuration for scheduled triggers
        schedule_type = data.get("schedule_type")
        schedule_time = data.get("schedule_time")
        schedule_day = data.get("schedule_day")
        schedule_timezone = data.get("schedule_timezone", "Asia/Seoul")
        skill_command = data.get("skill_command")
        model = data.get("model")
        execution_mode = data.get("execution_mode", "direct")
        team_id = data.get("team_id")

        # Validate schedule config for scheduled trigger
        if trigger_source == "scheduled":
            if not schedule_type or not schedule_time:
                return {
                    "error": "schedule_type and schedule_time required for scheduled trigger"
                }, HTTPStatus.BAD_REQUEST

        trigger_id = add_trigger(
            name=name,
            prompt_template=prompt_template,
            backend_type=backend_type,
            trigger_source=trigger_source,
            match_field_path=match_field_path,
            match_field_value=match_field_value,
            text_field_path=text_field_path,
            detection_keyword=detection_keyword,
            group_id=group_id,
            schedule_type=schedule_type,
            schedule_time=schedule_time,
            schedule_day=schedule_day,
            schedule_timezone=schedule_timezone,
            skill_command=skill_command,
            model=model,
            execution_mode=execution_mode,
            team_id=team_id,
        )
        if trigger_id:
            # Register with scheduler if scheduled
            if trigger_source == "scheduled":
                trigger = get_trigger(trigger_id)
                if trigger:
                    SchedulerService.schedule_trigger(trigger)

            return {
                "message": "Trigger created",
                "trigger_id": trigger_id,
                "name": name,
            }, HTTPStatus.CREATED
        else:
            return {"error": "Failed to create trigger"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    def update_trigger(trigger_id: str, data: dict) -> Tuple[dict, HTTPStatus]:
        """Update a trigger."""
        trigger = get_trigger(trigger_id)
        if not trigger:
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

        group_id = data.get("group_id")
        if group_id is not None:
            try:
                group_id = int(group_id)
            except (ValueError, TypeError):
                return {"error": "group_id must be a number"}, HTTPStatus.BAD_REQUEST

        success = update_trigger(
            trigger_id,
            name=data.get("name"),
            group_id=group_id,
            detection_keyword=data.get("detection_keyword"),
            prompt_template=data.get("prompt_template"),
            backend_type=data.get("backend_type"),
            trigger_source=data.get("trigger_source"),
            match_field_path=data.get("match_field_path"),
            match_field_value=data.get("match_field_value"),
            text_field_path=data.get("text_field_path"),
            enabled=data.get("enabled"),
            schedule_type=data.get("schedule_type"),
            schedule_time=data.get("schedule_time"),
            schedule_day=data.get("schedule_day"),
            schedule_timezone=data.get("schedule_timezone"),
            skill_command=data.get("skill_command"),
            model=data.get("model"),
            execution_mode=data.get("execution_mode"),
            team_id=data.get("team_id"),
        )
        if success:
            # Reschedule if schedule-related fields changed
            SchedulerService.reschedule_trigger(trigger_id)
            return {"message": "Trigger updated"}, HTTPStatus.OK
        else:
            return {"error": "No changes made"}, HTTPStatus.BAD_REQUEST

    @staticmethod
    def delete_trigger(trigger_id: str) -> Tuple[dict, HTTPStatus]:
        """Delete a trigger (non-predefined only)."""
        trigger = get_trigger(trigger_id)
        if not trigger:
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

        if trigger["is_predefined"]:
            return {"error": "Cannot delete predefined trigger"}, HTTPStatus.FORBIDDEN

        # Unschedule if it was scheduled
        SchedulerService.unschedule_trigger(trigger_id)

        success = delete_trigger(trigger_id)
        if success:
            return {"message": "Trigger deleted"}, HTTPStatus.OK
        else:
            return {"error": "Failed to delete trigger"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    def list_paths(trigger_id: str) -> Tuple[dict, HTTPStatus]:
        """List all paths for a trigger."""
        trigger = get_trigger(trigger_id)
        if not trigger:
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

        paths = list_paths_for_trigger(trigger_id)
        return {"paths": paths}, HTTPStatus.OK

    @staticmethod
    def add_path(trigger_id: str, data: dict) -> Tuple[dict, HTTPStatus]:
        """Add a project path or GitHub repo to a trigger."""
        trigger = get_trigger(trigger_id)
        if not trigger:
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

        github_repo_url = data.get("github_repo_url")
        local_project_path = data.get("local_project_path")

        if github_repo_url:
            # Validate GitHub URL format and accessibility
            if not GitHubService.validate_repo_url(github_repo_url):
                return {
                    "error": f"Invalid or inaccessible GitHub repo: {github_repo_url}"
                }, HTTPStatus.BAD_REQUEST

            success = add_github_repo(trigger_id, github_repo_url)
            if success:
                return {
                    "message": "GitHub repository added",
                    "github_repo_url": github_repo_url,
                    "path_type": "github",
                }, HTTPStatus.CREATED
            else:
                return {"error": "Repository already exists for this trigger"}, HTTPStatus.CONFLICT

        elif local_project_path:
            # Validate path exists and is a directory
            path_obj = Path(local_project_path)
            if not path_obj.exists():
                return {
                    "error": f"Path does not exist: {local_project_path}"
                }, HTTPStatus.BAD_REQUEST
            if not path_obj.is_dir():
                return {
                    "error": f"Path is not a directory: {local_project_path}"
                }, HTTPStatus.BAD_REQUEST

            success = add_project_path(trigger_id, local_project_path)
            if success:
                return {
                    "message": "Path added",
                    "local_project_path": local_project_path,
                    "path_type": "local",
                }, HTTPStatus.CREATED
            else:
                return {"error": "Path already exists for this trigger"}, HTTPStatus.CONFLICT

        else:
            return {
                "error": "local_project_path or github_repo_url required"
            }, HTTPStatus.BAD_REQUEST

    @staticmethod
    def remove_path(trigger_id: str, data: dict) -> Tuple[dict, HTTPStatus]:
        """Remove a project path or GitHub repo from a trigger."""
        trigger = get_trigger(trigger_id)
        if not trigger:
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

        github_repo_url = data.get("github_repo_url")
        local_project_path = data.get("local_project_path")

        if github_repo_url:
            success = remove_github_repo(trigger_id, github_repo_url)
            if success:
                return {"message": "GitHub repository removed"}, HTTPStatus.OK
            else:
                return {"error": "Repository not found"}, HTTPStatus.NOT_FOUND

        elif local_project_path:
            success = remove_project_path(trigger_id, local_project_path)
            if success:
                return {"message": "Path removed"}, HTTPStatus.OK
            else:
                return {"error": "Path not found"}, HTTPStatus.NOT_FOUND

        else:
            return {
                "error": "local_project_path or github_repo_url required"
            }, HTTPStatus.BAD_REQUEST

    @staticmethod
    def add_project(trigger_id: str, project_id: str) -> Tuple[dict, HTTPStatus]:
        """Add a project reference to a trigger."""
        trigger = get_trigger(trigger_id)
        if not trigger:
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

        # Validate project exists and has github_repo
        project = get_project(project_id)
        if not project:
            return {"error": "Project not found"}, HTTPStatus.NOT_FOUND

        if not project.get("github_repo"):
            return {
                "error": "Project does not have a GitHub repository configured"
            }, HTTPStatus.BAD_REQUEST

        success = add_project_to_trigger(trigger_id, project_id)
        if success:
            return {
                "message": "Project added to trigger",
                "project_id": project_id,
                "project_name": project.get("name"),
                "github_repo": project.get("github_repo"),
            }, HTTPStatus.CREATED
        else:
            return {"error": "Project already added"}, HTTPStatus.CONFLICT

    @staticmethod
    def remove_project(trigger_id: str, project_id: str) -> Tuple[dict, HTTPStatus]:
        """Remove a project reference from a trigger."""
        trigger = get_trigger(trigger_id)
        if not trigger:
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

        success = remove_project_from_trigger(trigger_id, project_id)
        if success:
            return {"message": "Project removed from trigger"}, HTTPStatus.OK
        else:
            return {"error": "Project not found on this trigger"}, HTTPStatus.NOT_FOUND

    @staticmethod
    def run(trigger_id: str, message: str = "") -> Tuple[dict, HTTPStatus]:
        """Execute a trigger manually. Spawns background thread.

        Handles: trigger lookup, enabled check, already-running check,
        thread spawning, and execution_id capture.
        """
        import threading

        from ..services.execution_log_service import ExecutionLogService

        trigger = get_trigger(trigger_id)
        if not trigger:
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

        if not trigger.get("enabled", True):
            return {"error": "Trigger is disabled"}, HTTPStatus.BAD_REQUEST

        running = ExecutionLogService.get_running_for_trigger(trigger_id)
        if running:
            return {
                "error": "Trigger is already running",
                "execution_id": running["execution_id"],
            }, HTTPStatus.CONFLICT

        execution_result = {"execution_id": None}

        def run_and_capture():
            execution_result["execution_id"] = ExecutionService.run_trigger(
                trigger, message, None, "manual"
            )

        thread = threading.Thread(target=run_and_capture, daemon=True)
        thread.start()
        thread.join(timeout=0.5)

        return {
            "message": f"Trigger '{trigger['name']}' started",
            "trigger_id": trigger_id,
            "status": "running",
            "execution_id": execution_result.get("execution_id"),
        }, HTTPStatus.ACCEPTED

    @staticmethod
    def update_auto_resolve(trigger_id: str, auto_resolve: bool) -> Tuple[dict, HTTPStatus]:
        """Enable/disable auto-resolve for a trigger (security trigger only)."""
        trigger = get_trigger(trigger_id)
        if not trigger:
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND

        if trigger_id != PREDEFINED_TRIGGER_ID:
            return {
                "error": "Auto-resolve is only available for the security trigger"
            }, HTTPStatus.BAD_REQUEST

        success = update_trigger_auto_resolve(trigger_id, auto_resolve)
        if success:
            return {
                "message": f"Auto-resolve {'enabled' if auto_resolve else 'disabled'}"
            }, HTTPStatus.OK
        else:
            return {"error": "Failed to update"}, HTTPStatus.INTERNAL_SERVER_ERROR
