"""GRD Sync Service — incremental SHA256 file-to-DB sync.

Parses .planning/ markdown files (ROADMAP.md, PLAN.md, SUMMARY.md) into SQLite
records (milestones, project_phases, project_plans) with SHA256 content hashing
for incremental sync — unchanged files are skipped.
"""

import datetime
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional


class _SafeEncoder(json.JSONEncoder):
    """JSON encoder that handles date/datetime objects from YAML frontmatter."""

    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        return super().default(obj)


from app.database import (
    add_milestone,
    add_project_phase,
    add_project_plan,
    get_milestones_by_project,
    get_phases_by_milestone,
    get_plans_by_phase,
    get_project_sync_state,
    update_milestone,
    update_project_phase,
    update_project_plan,
    upsert_project_sync_state,
)
from app.utils.plugin_format import parse_yaml_frontmatter

logger = logging.getLogger(__name__)


def _sha256(content: str) -> str:
    """SHA256 hash for incremental sync comparison."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class GrdSyncService:
    """Parse .planning/ markdown files into SQLite records with SHA256 incremental sync."""

    @classmethod
    def sync_project(cls, project_id: str, planning_dir: str) -> dict:
        """Full sync of a project's .planning/ directory.

        Args:
            project_id: The project ID in Agented's database.
            planning_dir: Absolute path to the .planning/ directory.

        Returns:
            {"synced": int, "skipped": int, "errors": list[str]}
        """
        planning_path = Path(planning_dir)
        if not planning_path.exists():
            return {
                "synced": 0,
                "skipped": 0,
                "errors": [f".planning/ not found at {planning_dir}"],
            }

        results = {"synced": 0, "skipped": 0, "errors": []}
        milestone_id = None

        # Step 1: Process ROADMAP.md -> milestone + phases
        roadmap_file = planning_path / "ROADMAP.md"
        if roadmap_file.exists():
            content = roadmap_file.read_text(encoding="utf-8")
            file_hash = _sha256(content)
            cached = get_project_sync_state(project_id, str(roadmap_file))
            if cached and cached["content_hash"] == file_hash:
                results["skipped"] += 1
                # Still need the milestone_id for phase dir sync
                if cached.get("entity_id"):
                    milestone_id = cached["entity_id"]
            else:
                try:
                    milestone_id = cls._sync_roadmap(project_id, content)
                    upsert_project_sync_state(
                        project_id,
                        str(roadmap_file),
                        file_hash,
                        entity_type="milestone",
                        entity_id=milestone_id,
                    )
                    results["synced"] += 1
                except Exception as e:
                    logger.error(f"Error syncing ROADMAP.md: {e}")
                    results["errors"].append(f"ROADMAP.md: {e}")

        # If no milestone_id yet, try to get from existing milestones
        if milestone_id is None:
            existing_milestones = get_milestones_by_project(project_id)
            if existing_milestones:
                milestone_id = existing_milestones[0]["id"]

        # Step 2: Walk phases/ subdirectory
        phases_dir = planning_path / "phases"
        if phases_dir.exists() and milestone_id:
            for phase_dir in sorted(phases_dir.iterdir()):
                if not phase_dir.is_dir():
                    continue
                if not re.match(r"^\d+-(.+)$", phase_dir.name):
                    continue
                cls._sync_phase_dir(project_id, phase_dir, milestone_id, results)

        return results

    @classmethod
    def _sync_roadmap(cls, project_id: str, content: str) -> Optional[str]:
        """Parse ROADMAP.md and upsert milestone + phase records. Returns milestone_id."""
        # Extract milestone version from first heading: # Roadmap — vX.Y.Z ...
        version_match = re.search(r"v(\d+\.\d+(?:\.\d+)?)", content)
        version = "v" + version_match.group(1) if version_match else "v0.0.0"

        # Extract milestone title from first # heading
        title_match = re.search(r"^#\s+(.+?)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "Milestone"

        # Upsert milestone: check existing milestones for matching version
        existing = get_milestones_by_project(project_id)
        milestone_id = None
        for ms in existing:
            if ms.get("version") == version:
                update_milestone(ms["id"], title=title, roadmap_json=content[:10000])
                milestone_id = ms["id"]
                break

        if milestone_id is None:
            milestone_id = add_milestone(
                project_id, version=version, title=title, roadmap_json=content[:10000]
            )

        if not milestone_id:
            raise ValueError(f"Failed to create milestone for version {version}")

        # Extract phases from ## Phase N: Name headings
        phase_pattern = re.compile(r"^## Phase (\d+):\s*(.+?)$", re.MULTILINE)
        phase_matches = list(phase_pattern.finditer(content))

        for i, match in enumerate(phase_matches):
            phase_number = int(match.group(1))
            phase_name = match.group(2).strip()

            # Extract the section text between this heading and the next ## Phase heading
            section_start = match.start()
            if i + 1 < len(phase_matches):
                section_end = phase_matches[i + 1].start()
            else:
                # Find the next ## heading (any) or end of content
                next_heading = re.search(r"\n## ", content[match.end() :])
                if next_heading:
                    section_end = match.end() + next_heading.start()
                else:
                    section_end = len(content)

            section = content[section_start:section_end]

            # Extract metadata from section
            goal_match = re.search(r"\*\*Goal:\*\*\s*([^\n]+)", section)
            goal = goal_match.group(1).strip() if goal_match else None

            verif_match = re.search(r"\*\*Verification Level:\*\*\s*([^\n]+)", section)
            verification_level = verif_match.group(1).strip() if verif_match else "sanity"

            deps_match = re.search(r"\*\*Dependencies:\*\*\s*([^\n]+)", section)
            dependencies = deps_match.group(1).strip() if deps_match else None

            # Upsert phase: check existing phases for matching phase_number
            existing_phases = get_phases_by_milestone(milestone_id)
            phase_id = None
            for ep in existing_phases:
                if ep.get("phase_number") == phase_number:
                    update_project_phase(
                        ep["id"],
                        name=phase_name,
                        goal=goal,
                        verification_level=verification_level,
                        dependencies=dependencies,
                    )
                    phase_id = ep["id"]
                    break

            if phase_id is None:
                phase_id = add_project_phase(
                    milestone_id,
                    phase_number=phase_number,
                    name=phase_name,
                    goal=goal,
                    verification_level=verification_level,
                    dependencies=dependencies,
                )

            if not phase_id:
                logger.warning(f"Failed to upsert phase {phase_number}: {phase_name}")

        logger.info(
            f"Synced ROADMAP.md: milestone={milestone_id}, "
            f"phases={len(phase_matches)} for project {project_id}"
        )
        return milestone_id

    @classmethod
    def _sync_phase_dir(
        cls, project_id: str, phase_dir: Path, milestone_id: str, results: dict
    ) -> None:
        """Sync a single phase directory's PLAN.md and SUMMARY.md files.

        Args:
            project_id: The project ID.
            phase_dir: Path to the phase directory (e.g., .planning/phases/42-foundation-...).
            milestone_id: The milestone ID these plans belong to.
            results: Mutable results dict to update synced/skipped/errors counts.
        """
        # Extract phase number from directory name
        dir_match = re.match(r"^(\d+)-(.+)$", phase_dir.name)
        if not dir_match:
            return
        phase_number = int(dir_match.group(1))

        # Find the phase_id for this milestone + phase_number
        existing_phases = get_phases_by_milestone(milestone_id)
        phase_id = None
        for ep in existing_phases:
            if ep.get("phase_number") == phase_number:
                phase_id = ep["id"]
                break

        if not phase_id:
            # Phase not in DB yet — may not have been in ROADMAP.md, skip
            logger.debug(
                f"Phase {phase_number} not found in DB, skipping directory {phase_dir.name}"
            )
            return

        # Glob for PLAN files: handles both *-PLAN.md (e.g., 42-01-PLAN.md) and PLAN.md
        plan_files = sorted(phase_dir.glob("*-PLAN.md"))
        single_plan = phase_dir / "PLAN.md"
        if single_plan.exists() and single_plan not in plan_files:
            plan_files.append(single_plan)

        for plan_file in plan_files:
            cls._sync_plan_file(project_id, plan_file, phase_id, results)

        # Glob for SUMMARY files: handles *-SUMMARY.md
        summary_files = sorted(phase_dir.glob("*-SUMMARY.md"))
        for summary_file in summary_files:
            cls._sync_summary_file(project_id, summary_file, phase_id, results)

    @classmethod
    def _sync_plan_file(
        cls, project_id: str, plan_file: Path, phase_id: str, results: dict
    ) -> None:
        """Sync a single PLAN.md file into the project_plans table."""
        content = plan_file.read_text(encoding="utf-8")
        file_hash = _sha256(content)
        cached = get_project_sync_state(project_id, str(plan_file))

        if cached and cached["content_hash"] == file_hash:
            results["skipped"] += 1
            return

        try:
            frontmatter, body = parse_yaml_frontmatter(content)

            # Coerce plan number from frontmatter
            plan_number = int(frontmatter.get("plan", 0))

            # Extract title from the plan's objective or first heading
            title = frontmatter.get("phase", f"Plan {plan_number}")
            # Try to extract a more descriptive title from the body
            obj_match = re.search(r"<objective>\s*\n?(.*?)(?:\n|</objective>)", body, re.DOTALL)
            if obj_match:
                obj_text = obj_match.group(1).strip()
                # Use first sentence as title (up to 200 chars)
                first_line = obj_text.split("\n")[0].strip()
                if first_line:
                    title = first_line[:200]

            # Build tasks_json with plan metadata (all metadata in single column)
            tasks_data = {
                "verification_level": frontmatter.get("verification_level"),
                "wave": frontmatter.get("wave"),
                "plan_type": frontmatter.get("type"),
                "autonomous": frontmatter.get("autonomous"),
                "depends_on": frontmatter.get("depends_on") or [],
                "files_modified": frontmatter.get("files_modified") or [],
                "must_haves": frontmatter.get("must_haves") or {},
            }
            tasks_json_str = json.dumps(tasks_data, cls=_SafeEncoder)

            # Upsert plan: check existing plans for matching plan_number
            existing_plans = get_plans_by_phase(phase_id)
            plan_id = None
            for ep in existing_plans:
                if ep.get("plan_number") == plan_number:
                    update_project_plan(
                        ep["id"],
                        title=title,
                        tasks_json=tasks_json_str,
                    )
                    plan_id = ep["id"]
                    break

            if plan_id is None:
                plan_id = add_project_plan(
                    phase_id,
                    plan_number=plan_number,
                    title=title,
                    tasks_json=tasks_json_str,
                )

            if plan_id:
                upsert_project_sync_state(
                    project_id,
                    str(plan_file),
                    file_hash,
                    entity_type="plan",
                    entity_id=plan_id,
                )
                results["synced"] += 1
            else:
                results["errors"].append(f"{plan_file.name}: Failed to upsert plan")

        except Exception as e:
            logger.error(f"Error syncing plan file {plan_file}: {e}")
            results["errors"].append(f"{plan_file.name}: {e}")

    @classmethod
    def _sync_summary_file(
        cls, project_id: str, summary_file: Path, phase_id: str, results: dict
    ) -> None:
        """Sync a single SUMMARY.md file — merges summary data into existing plan's tasks_json."""
        content = summary_file.read_text(encoding="utf-8")
        file_hash = _sha256(content)
        cached = get_project_sync_state(project_id, str(summary_file))

        if cached and cached["content_hash"] == file_hash:
            results["skipped"] += 1
            return

        try:
            frontmatter, body = parse_yaml_frontmatter(content)
            plan_number = int(frontmatter.get("plan", 0))

            # Find the matching plan in DB
            existing_plans = get_plans_by_phase(phase_id)
            plan_id = None
            for ep in existing_plans:
                if ep.get("plan_number") == plan_number:
                    plan_id = ep["id"]
                    break

            if not plan_id:
                # No matching plan for this summary — skip
                results["skipped"] += 1
                return

            # Build summary data from frontmatter
            summary_data = {
                "subsystem": frontmatter.get("subsystem"),
                "tags": frontmatter.get("tags") or [],
                "decisions": frontmatter.get("decisions") or [],
                "metrics": frontmatter.get("metrics") or {},
                "dependency_graph": frontmatter.get("dependency_graph") or {},
                "tech_stack": frontmatter.get("tech_stack") or {},
                "key_files": frontmatter.get("key_files") or {},
            }

            # Merge into existing tasks_json
            from app.database import get_project_plan

            existing_plan = get_project_plan(plan_id)
            if existing_plan and existing_plan.get("tasks_json"):
                try:
                    merged = json.loads(existing_plan["tasks_json"])
                except (json.JSONDecodeError, TypeError):
                    merged = {}
            else:
                merged = {}

            merged["summary"] = summary_data
            merged_json = json.dumps(merged, cls=_SafeEncoder)

            update_project_plan(plan_id, tasks_json=merged_json, status="completed")

            upsert_project_sync_state(
                project_id,
                str(summary_file),
                file_hash,
                entity_type="plan",
                entity_id=plan_id,
            )
            results["synced"] += 1

        except Exception as e:
            logger.error(f"Error syncing summary file {summary_file}: {e}")
            results["errors"].append(f"{summary_file.name}: {e}")

    @classmethod
    def sync_on_session_complete(cls, project_id: str, session_id: str):
        """Sync .planning/ files to DB after a planning session completes.

        Called by ProjectSessionManager._handle_session_exit() for GRD-related sessions.
        Runs synchronously BEFORE the complete event is broadcast to ensure
        the frontend sees fresh data when it refreshes.
        """
        from app.database import get_project as _get_project

        project = _get_project(project_id)
        if not project:
            logger.warning("sync_on_session_complete: project %s not found", project_id)
            return

        local_path = project.get("local_path")
        if not local_path:
            return

        planning_dir = str(Path(local_path).expanduser().resolve() / ".planning")
        if not Path(planning_dir).is_dir():
            return

        try:
            result = cls.sync_project(project_id, planning_dir)
            logger.info(
                "Session-completion sync for project %s: synced=%d, skipped=%d",
                project_id,
                result["synced"],
                result["skipped"],
            )
        except Exception as e:
            logger.error("Session-completion sync failed for project %s: %s", project_id, e)
