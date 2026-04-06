"""Project-scoped SA/team instance lifecycle management service.

Provides creation, deletion, worktree management, and session bootstrapping
for project SA instances and project team instances.
"""

import logging
import os
import subprocess
import threading
from typing import Dict, List, Optional

from ..db.connection import get_connection
from ..db.project_sa_instances import (
    create_project_sa_instance,
    delete_project_sa_instance,
    get_project_sa_instance,
    get_project_sa_instance_by_project_and_sa,
    get_project_sa_instances_without_worktree,
    update_project_sa_instance,
)
from ..db.project_team_instances import (
    create_project_team_instance,
    delete_project_team_instance,
)
from ..db.projects import get_project
from ..db.super_agents import (
    get_sessions_for_instance,
    get_super_agent,
    update_super_agent_session,
)
from ..db.teams import get_team_members
from .super_agent_session_service import SuperAgentSessionService

logger = logging.getLogger(__name__)


class InstanceService:
    """Service for project-scoped SA/team instance lifecycle.

    Uses classmethod singleton pattern (no instantiation needed).
    Thread-safe via RLock for concurrent access.
    """

    _lock = threading.RLock()

    # ------------------------------------------------------------------
    # Public: team instance creation
    # ------------------------------------------------------------------

    @classmethod
    def create_team_instances(cls, project_id: str, team_id: str) -> Optional[Dict]:
        """Create a project team instance and SA instances for each team member.

        Single entry point for team instance creation. Creates the team instance
        row and an SA instance for each super_agent member in the team.

        Worktree creation and session bootstrapping happen after the DB transaction
        commits so that partial git failures don't roll back valid DB state.

        Returns:
            Dict with team_instance_id and sa_instances list, or None on failure.
        """
        with cls._lock:
            project = get_project(project_id)
            if not project:
                logger.error("create_team_instances: project %s not found", project_id)
                return None

            members = get_team_members(team_id)
            if not members:
                logger.warning("create_team_instances: team %s has no members", team_id)

            # --- DB transaction: create team instance + SA instance rows ---
            team_instance_id = None
            sa_instance_rows: List[Dict] = []

            with get_connection() as conn:
                from ..db.ids import _get_unique_psa_id, _get_unique_pti_id

                # Create project_team_instance row
                try:
                    pti_id = _get_unique_pti_id(conn)
                    conn.execute(
                        """
                        INSERT INTO project_team_instances
                        (id, project_id, template_team_id, config_overrides)
                        VALUES (?, ?, ?, NULL)
                        """,
                        (pti_id, project_id, team_id),
                    )
                    team_instance_id = pti_id
                except Exception:
                    logger.exception(
                        "Failed to create team instance for project=%s team=%s",
                        project_id,
                        team_id,
                    )
                    return None

                # Create SA instances for each super_agent member
                for member in members:
                    sa_id = member.get("super_agent_id")
                    if not sa_id:
                        continue  # Skip non-super-agent members

                    try:
                        psa_id = _get_unique_psa_id(conn)
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO project_sa_instances
                            (id, project_id, template_sa_id, worktree_path,
                             default_chat_mode, config_overrides)
                            VALUES (?, ?, ?, NULL, 'management', NULL)
                            """,
                            (psa_id, project_id, sa_id),
                        )
                        if conn.execute("SELECT changes()").fetchone()[0] > 0:
                            sa_instance_rows.append(
                                {
                                    "id": psa_id,
                                    "template_sa_id": sa_id,
                                }
                            )
                        else:
                            # Already existed (UNIQUE constraint), find existing
                            existing = conn.execute(
                                "SELECT id FROM project_sa_instances "
                                "WHERE project_id = ? AND template_sa_id = ?",
                                (project_id, sa_id),
                            ).fetchone()
                            if existing:
                                sa_instance_rows.append(
                                    {
                                        "id": existing[0],
                                        "template_sa_id": sa_id,
                                    }
                                )
                    except Exception:
                        logger.exception(
                            "Failed to create SA instance for sa=%s in project=%s",
                            sa_id,
                            project_id,
                        )

                conn.commit()

            # --- Post-transaction: create worktrees and sessions ---
            result_sa_instances = []
            for sa_row in sa_instance_rows:
                psa_id = sa_row["id"]
                sa_id = sa_row["template_sa_id"]

                # Create worktree
                worktree_path = cls._create_worktree_for_instance(project, sa_id, psa_id)
                if worktree_path:
                    update_project_sa_instance(psa_id, worktree_path=worktree_path)

                # Create initial session
                session_id = cls._create_initial_session(sa_id, psa_id)

                result_sa_instances.append(
                    {
                        "id": psa_id,
                        "template_sa_id": sa_id,
                        "worktree_path": worktree_path,
                        "session_id": session_id,
                    }
                )

            return {
                "team_instance_id": team_instance_id,
                "sa_instances": result_sa_instances,
            }

    # ------------------------------------------------------------------
    # Public: single SA instance creation
    # ------------------------------------------------------------------

    @classmethod
    def create_sa_instance(cls, project_id: str, super_agent_id: str) -> Optional[Dict]:
        """Create a single SA instance for a project.

        Used for manager SA or standalone SA instances.

        Returns:
            Dict with instance info, or None on failure.
        """
        with cls._lock:
            project = get_project(project_id)
            if not project:
                logger.error("create_sa_instance: project %s not found", project_id)
                return None

            sa = get_super_agent(super_agent_id)
            if not sa:
                logger.error("create_sa_instance: super_agent %s not found", super_agent_id)
                return None

            # Create DB row
            psa_id = create_project_sa_instance(project_id, super_agent_id)
            if not psa_id:
                # May already exist (idempotent)
                existing = get_project_sa_instance_by_project_and_sa(project_id, super_agent_id)
                if existing:
                    return {
                        "id": existing["id"],
                        "template_sa_id": super_agent_id,
                        "worktree_path": existing["worktree_path"],
                        "session_id": None,
                    }
                logger.error(
                    "create_sa_instance: failed to create instance for sa=%s project=%s",
                    super_agent_id,
                    project_id,
                )
                return None

            # Create worktree
            worktree_path = cls._create_worktree_for_instance(project, super_agent_id, psa_id)
            if worktree_path:
                update_project_sa_instance(psa_id, worktree_path=worktree_path)

            # Create initial session
            session_id = cls._create_initial_session(super_agent_id, psa_id)

            return {
                "id": psa_id,
                "template_sa_id": super_agent_id,
                "worktree_path": worktree_path,
                "session_id": session_id,
            }

    # ------------------------------------------------------------------
    # Public: manager instance lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def ensure_manager_instance(cls, project_id: str) -> Optional[Dict]:
        """Ensure a manager SA instance exists for a project.

        Called when project.manager_super_agent_id is set or changed.
        If the manager SA already has an instance, returns it; otherwise creates one.

        Returns:
            Dict with instance info, or None if no manager SA is set.
        """
        project = get_project(project_id)
        if not project:
            logger.error("ensure_manager_instance: project %s not found", project_id)
            return None

        manager_sa_id = project.get("manager_super_agent_id")
        if not manager_sa_id:
            return None

        # Check if instance already exists
        existing = get_project_sa_instance_by_project_and_sa(project_id, manager_sa_id)
        if existing:
            return {
                "id": existing["id"],
                "template_sa_id": manager_sa_id,
                "worktree_path": existing["worktree_path"],
                "session_id": None,
            }

        return cls.create_sa_instance(project_id, manager_sa_id)

    @classmethod
    def cleanup_manager_instance(cls, project_id: str, old_sa_id: str) -> bool:
        """Delete the instance for a removed/changed manager SA.

        Finds the instance for the (project_id, old_sa_id) pair and deletes it.

        Returns:
            True if an instance was found and deleted, False otherwise.
        """
        instance = get_project_sa_instance_by_project_and_sa(project_id, old_sa_id)
        if not instance:
            return False

        return cls.delete_instance(instance["id"])

    # ------------------------------------------------------------------
    # Public: instance deletion
    # ------------------------------------------------------------------

    @classmethod
    def delete_instance(cls, instance_id: str) -> bool:
        """Full cleanup of an SA instance.

        Ends active sessions, removes git worktree, and deletes the DB row.

        Returns:
            True on success, False if instance not found.
        """
        instance = get_project_sa_instance(instance_id)
        if not instance:
            logger.warning("delete_instance: instance %s not found", instance_id)
            return False

        # End active sessions
        sessions = get_sessions_for_instance(instance_id)
        for session in sessions:
            if session["status"] in ("active", "paused"):
                try:
                    SuperAgentSessionService.end_session(session["id"])
                except Exception:
                    logger.exception(
                        "Failed to end session %s for instance %s",
                        session["id"],
                        instance_id,
                    )

        # Remove worktree
        worktree_path = instance.get("worktree_path")
        if worktree_path:
            cls._remove_worktree(worktree_path)

        # Delete DB row
        return delete_project_sa_instance(instance_id)

    # ------------------------------------------------------------------
    # Public: worktree recovery
    # ------------------------------------------------------------------

    @classmethod
    def ensure_worktrees(cls) -> int:
        """Startup hook: create worktrees for all instances missing one.

        Queries all project_sa_instances where worktree_path IS NULL and
        attempts to create worktrees for each.

        Returns:
            Number of worktrees successfully created.
        """
        instances = get_project_sa_instances_without_worktree()
        created = 0

        for inst in instances:
            project = get_project(inst["project_id"])
            if not project:
                logger.warning(
                    "ensure_worktrees: project %s not found for instance %s",
                    inst["project_id"],
                    inst["id"],
                )
                continue

            worktree_path = cls._create_worktree_for_instance(
                project, inst["template_sa_id"], inst["id"]
            )
            if worktree_path:
                update_project_sa_instance(inst["id"], worktree_path=worktree_path)
                created += 1

        logger.info(
            "ensure_worktrees: created %d worktrees out of %d missing", created, len(instances)
        )
        return created

    @classmethod
    def ensure_worktree(cls, instance_id: str) -> Optional[str]:
        """Re-create a single worktree for recovery.

        Returns:
            Absolute worktree path on success, None on failure.
        """
        instance = get_project_sa_instance(instance_id)
        if not instance:
            logger.error("ensure_worktree: instance %s not found", instance_id)
            return None

        project = get_project(instance["project_id"])
        if not project:
            logger.error(
                "ensure_worktree: project %s not found for instance %s",
                instance["project_id"],
                instance_id,
            )
            return None

        worktree_path = cls._create_worktree_for_instance(
            project, instance["template_sa_id"], instance_id
        )
        if worktree_path:
            update_project_sa_instance(instance_id, worktree_path=worktree_path)

        return worktree_path

    # ------------------------------------------------------------------
    # Internal: worktree helpers
    # ------------------------------------------------------------------

    @classmethod
    def _create_worktree_for_instance(cls, project: dict, sa_id: str, psa_id: str) -> Optional[str]:
        """Look up the SA name and delegate to _create_worktree.

        Returns absolute worktree path on success, None on failure.
        """
        project_local_path = project.get("local_path")
        if not project_local_path:
            logger.warning(
                "_create_worktree_for_instance: project %s has no local_path",
                project["id"],
            )
            return None

        sa = get_super_agent(sa_id)
        sa_name = sa["name"] if sa else sa_id

        return cls._create_worktree(project_local_path, sa_name, psa_id)

    @classmethod
    def _create_worktree(cls, project_local_path: str, sa_name: str, psa_id: str) -> Optional[str]:
        """Create a git worktree for an SA instance.

        Runs: git -C {project_local_path} worktree add .worktrees/{sa_name_lower} -b instance/{psa_id}

        Returns:
            Absolute worktree path on success, None on failure.
        """
        if not project_local_path:
            logger.error("_create_worktree: project_local_path is empty")
            return None

        if not os.path.isdir(project_local_path):
            logger.error(
                "_create_worktree: project_local_path %s does not exist",
                project_local_path,
            )
            return None

        # Verify it's a git repo
        git_dir = os.path.join(project_local_path, ".git")
        if not os.path.exists(git_dir):
            logger.error("_create_worktree: %s is not a git repository", project_local_path)
            return None

        sa_name_lower = sa_name.lower().replace(" ", "-")
        worktree_rel = os.path.join(".worktrees", sa_name_lower)
        worktree_abs = os.path.join(project_local_path, worktree_rel)
        branch_name = f"instance/{psa_id}"

        # If worktree directory already exists, return it
        if os.path.isdir(worktree_abs):
            logger.info("_create_worktree: reusing existing worktree at %s", worktree_abs)
            return worktree_abs

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    project_local_path,
                    "worktree",
                    "add",
                    worktree_rel,
                    "-b",
                    branch_name,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # Branch may already exist -- retry without -b
                if "already exists" in result.stderr:
                    logger.info(
                        "_create_worktree: branch %s already exists, retrying without -b",
                        branch_name,
                    )
                    result = subprocess.run(
                        [
                            "git",
                            "-C",
                            project_local_path,
                            "worktree",
                            "add",
                            worktree_rel,
                            branch_name,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode != 0:
                        logger.error(
                            "_create_worktree: git worktree add failed (retry): %s",
                            result.stderr.strip(),
                        )
                        return None
                else:
                    logger.error(
                        "_create_worktree: git worktree add failed: %s",
                        result.stderr.strip(),
                    )
                    return None

            logger.info("_create_worktree: created worktree at %s", worktree_abs)
            return worktree_abs

        except subprocess.TimeoutExpired:
            logger.error("_create_worktree: git worktree add timed out")
            return None
        except Exception:
            logger.exception("_create_worktree: unexpected error")
            return None

    @classmethod
    def _remove_worktree(cls, worktree_path: str) -> bool:
        """Remove a git worktree.

        Runs: git worktree remove --force {worktree_path}
        Logs errors but does not raise.

        Returns:
            True on success, False on failure.
        """
        try:
            result = subprocess.run(
                ["git", "worktree", "remove", "--force", worktree_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(
                    "_remove_worktree: failed to remove %s: %s",
                    worktree_path,
                    result.stderr.strip(),
                )
                return False

            logger.info("_remove_worktree: removed worktree at %s", worktree_path)
            return True

        except subprocess.TimeoutExpired:
            logger.warning("_remove_worktree: git worktree remove timed out for %s", worktree_path)
            return False
        except Exception:
            logger.exception("_remove_worktree: unexpected error removing %s", worktree_path)
            return False

    # ------------------------------------------------------------------
    # Internal: session helper
    # ------------------------------------------------------------------

    @classmethod
    def _create_initial_session(cls, super_agent_id: str, instance_id: str) -> Optional[str]:
        """Create an initial persistent session for an SA instance.

        Returns:
            Session ID on success, None on failure.
        """
        try:
            session_id, error = SuperAgentSessionService.create_session(
                super_agent_id, instance_id=instance_id
            )
            if error:
                logger.warning(
                    "_create_initial_session: failed for sa=%s instance=%s: %s",
                    super_agent_id,
                    instance_id,
                    error,
                )
            return session_id
        except Exception:
            logger.exception(
                "_create_initial_session: unexpected error for sa=%s instance=%s",
                super_agent_id,
                instance_id,
            )
            return None

    # ------------------------------------------------------------------
    # Session-per-worktree lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def create_session_worktree(
        cls,
        project_id: str,
        super_agent_id: str,
        instance_id: str,
        title: str = None,
        session_type: str = "worker",
    ) -> Optional[Dict]:
        """Create a new worker session with its own git worktree.

        Returns dict with session_id, worktree_path, branch_name on success, None on failure.
        """
        with cls._lock:
            project = get_project(project_id)
            if not project or not project.get("local_path"):
                logger.error("create_session_worktree: project %s has no local_path", project_id)
                return None

            project_local_path = project["local_path"]
            if not os.path.isdir(project_local_path):
                logger.error(
                    "create_session_worktree: local_path %s does not exist", project_local_path
                )
                return None

            # Create the session first to get the ID
            session_id, error = SuperAgentSessionService.create_session(
                super_agent_id,
                instance_id=instance_id,
                project_id=project_id,
                title=title,
                session_type=session_type,
            )
            if error or not session_id:
                logger.error("create_session_worktree: session creation failed: %s", error)
                return None

            # Leader sessions don't get worktrees — they work on main
            if session_type == "leader":
                return {
                    "session_id": session_id,
                    "worktree_path": None,
                    "branch_name": None,
                }

            # Create worktree for worker session
            branch_name = f"session/{session_id}"
            worktree_rel = os.path.join(".worktrees", session_id)
            worktree_abs = os.path.join(project_local_path, worktree_rel)

            try:
                result = subprocess.run(
                    [
                        "git",
                        "-C",
                        project_local_path,
                        "worktree",
                        "add",
                        worktree_rel,
                        "-b",
                        branch_name,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    logger.error(
                        "create_session_worktree: git worktree add failed: %s",
                        result.stderr.strip(),
                    )
                    # Clean up the session we just created
                    SuperAgentSessionService.end_session(session_id)
                    return None
            except (subprocess.TimeoutExpired, Exception):
                logger.exception("create_session_worktree: git worktree add error")
                SuperAgentSessionService.end_session(session_id)
                return None

            # Update session with worktree info
            update_super_agent_session(
                session_id,
                worktree_path=worktree_abs,
                branch_name=branch_name,
            )
            # Also update in-memory session state
            SuperAgentSessionService.update_session_worktree(session_id, worktree_abs, branch_name)

            logger.info(
                "create_session_worktree: session=%s worktree=%s branch=%s",
                session_id,
                worktree_abs,
                branch_name,
            )
            return {
                "session_id": session_id,
                "worktree_path": worktree_abs,
                "branch_name": branch_name,
            }

    @classmethod
    def cleanup_session_worktree(cls, session_id: str, session: dict = None) -> bool:
        """Remove a session's worktree and delete its local branch.

        Returns True if cleanup succeeded (or no worktree to clean).
        """
        if session is None:
            from ..db.super_agents import get_super_agent_session

            session = get_super_agent_session(session_id)
        if not session:
            return True

        worktree_path = session.get("worktree_path")
        branch_name = session.get("branch_name")
        if not worktree_path:
            return True

        success = True
        # Remove worktree
        if os.path.isdir(worktree_path):
            if not cls._remove_worktree(worktree_path):
                success = False

        # Delete local branch if it exists
        if branch_name:
            project_id = session.get("project_id")
            if project_id:
                project = get_project(project_id)
                if project and project.get("local_path"):
                    try:
                        subprocess.run(
                            ["git", "-C", project["local_path"], "branch", "-D", branch_name],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                    except Exception:
                        logger.warning(
                            "cleanup_session_worktree: failed to delete branch %s", branch_name
                        )

        # Clear worktree fields in DB
        update_super_agent_session(session_id, worktree_path="", branch_name="")
        return success

    @classmethod
    def cleanup_orphan_session_worktrees(cls) -> int:
        """Remove worktrees that belong to ended sessions. Called at startup."""
        from ..db.super_agents import get_active_sessions_list

        active_sessions = get_active_sessions_list()
        active_worktrees = {
            s.get("worktree_path") for s in active_sessions if s.get("worktree_path")
        }

        cleaned = 0
        # Scan all project directories for .worktrees/sess-* dirs
        from ..db.projects import get_all_projects

        for project in get_all_projects():
            local_path = project.get("local_path")
            if not local_path:
                continue
            worktrees_dir = os.path.join(local_path, ".worktrees")
            if not os.path.isdir(worktrees_dir):
                continue
            for entry in os.listdir(worktrees_dir):
                if not entry.startswith("sess-"):
                    continue
                full_path = os.path.join(worktrees_dir, entry)
                if full_path not in active_worktrees:
                    logger.info("cleanup_orphan_session_worktrees: removing %s", full_path)
                    cls._remove_worktree(full_path)
                    cleaned += 1

        if cleaned:
            logger.info("cleanup_orphan_session_worktrees: removed %d orphan worktrees", cleaned)
        return cleaned
