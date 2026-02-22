"""Sync persistence service — DB-to-disk and disk-to-DB synchronization."""

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Optional

from app.database import (
    get_agent,
    get_command,
    get_hook,
    get_rule,
    get_sync_state,
    get_sync_states_for_plugin,
    get_user_skill,
    update_agent,
    update_command,
    update_hook,
    update_rule,
    update_sync_state,
    update_user_skill,
)
from app.utils.plugin_format import (
    _slugify,
    generate_agent_md,
    generate_command_md,
    generate_hooks_json,
    generate_skill_md,
    parse_yaml_frontmatter,
)

log = logging.getLogger(__name__)


class SyncService:
    """Service for incremental DB-to-disk sync and bidirectional file watching.

    All methods are static/class methods following existing service patterns.
    Uses content hashing (SHA-256) to detect changes and skip unnecessary writes.
    """

    # Class-level watcher registry keyed by plugin_id
    _watchers: dict = {}

    # Paths currently being written by SyncService (for sync loop prevention)
    _syncing_paths: set[str] = set()

    # Lock for thread-safe watcher registry access
    _watcher_lock = threading.Lock()

    @staticmethod
    def sync_entity_to_disk(
        entity_type: str, entity_id: str, plugin_id: str, plugin_dir: str
    ) -> bool:
        """Sync a single entity from DB to disk if its content has changed.

        Args:
            entity_type: One of 'agent', 'skill', 'command', 'hook', 'rule'.
            entity_id: The entity's ID in the database.
            plugin_id: The plugin this entity belongs to.
            plugin_dir: The base directory of the plugin on disk.

        Returns:
            True if file was written (content changed), False if skipped (no change).
        """
        # Load entity from DB
        entity = SyncService._load_entity(entity_type, entity_id)
        if entity is None:
            log.warning("Entity not found: %s %s", entity_type, entity_id)
            return False

        # Generate file content and determine target path
        if entity_type in ("hook", "rule"):
            # Hooks and rules are aggregated into hooks.json -- need all of them
            file_content, target_path = SyncService._generate_hooks_bundle(plugin_id, plugin_dir)
        else:
            file_content = SyncService._generate_entity_content(entity_type, entity)
            target_path = SyncService._entity_file_path(entity_type, entity, plugin_dir)

        if file_content is None or target_path is None:
            log.warning("Could not generate content for %s %s", entity_type, entity_id)
            return False

        # Compute hash and check against existing sync state
        new_hash = hashlib.sha256(file_content.encode("utf-8")).hexdigest()

        sync_state = get_sync_state(plugin_id, entity_type, entity_id)
        if sync_state and sync_state.get("content_hash") == new_hash:
            log.debug("No changes for %s %s, skipping", entity_type, entity_id)
            return False

        # Write file to disk with sync loop prevention
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        abs_path = str(target.resolve())
        SyncService._syncing_paths.add(abs_path)
        try:
            target.write_text(file_content, encoding="utf-8")
        finally:
            # Small delay before removing to ensure watcher events pass
            SyncService._syncing_paths.discard(abs_path)

        # Update sync state
        update_sync_state(
            plugin_id=plugin_id,
            entity_type=entity_type,
            entity_id=entity_id,
            content_hash=new_hash,
            sync_direction="to_disk",
        )

        log.info("Synced %s %s to disk: %s", entity_type, entity_id, target_path)
        return True

    @staticmethod
    def sync_all_to_disk(plugin_id: str, plugin_dir: str) -> dict:
        """Sync all entities for a plugin from DB to disk.

        Args:
            plugin_id: The plugin ID to sync.
            plugin_dir: The base directory of the plugin on disk.

        Returns:
            Summary dict: {"synced": count, "skipped": count, "errors": count}
        """
        sync_states = get_sync_states_for_plugin(plugin_id)
        synced = 0
        skipped = 0
        errors = 0

        for state in sync_states:
            entity_type = state.get("entity_type", "")
            entity_id = state.get("entity_id", "")
            try:
                result = SyncService.sync_entity_to_disk(
                    entity_type, entity_id, plugin_id, plugin_dir
                )
                if result:
                    synced += 1
                else:
                    skipped += 1
            except Exception:
                log.exception("Error syncing %s %s to disk", entity_type, entity_id)
                errors += 1

        return {"synced": synced, "skipped": skipped, "errors": errors}

    @staticmethod
    def sync_file_to_db(file_path: str, plugin_id: str, plugin_dir: str) -> bool:
        """Sync a file from disk back to the database.

        Determines entity type from file path, parses content, and updates DB.

        Args:
            file_path: Absolute path to the changed file.
            plugin_id: The plugin this file belongs to.
            plugin_dir: The base directory of the plugin on disk.

        Returns:
            True if DB was updated, False if skipped.
        """
        rel_path = str(Path(file_path).relative_to(plugin_dir))

        # Determine entity type from relative path
        entity_type = SyncService._detect_entity_type(rel_path)
        if entity_type is None:
            log.debug("Unrecognized file path pattern: %s", rel_path)
            return False

        # Read file content
        try:
            file_content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            log.exception("Error reading file: %s", file_path)
            return False

        # Compute hash
        new_hash = hashlib.sha256(file_content.encode("utf-8")).hexdigest()

        # Find matching sync state entry
        sync_state = SyncService._find_sync_state_by_path(plugin_id, entity_type, file_path)
        if sync_state and sync_state.get("content_hash") == new_hash:
            log.debug("File unchanged: %s", file_path)
            return False

        if not sync_state:
            log.warning(
                "No sync state found for %s at %s (plugin %s)",
                entity_type,
                file_path,
                plugin_id,
            )
            return False

        entity_id = sync_state.get("entity_id", "")

        # Parse and update DB
        try:
            if entity_type == "agent":
                SyncService._update_agent_from_file(entity_id, file_content)
            elif entity_type == "skill":
                SyncService._update_skill_from_file(entity_id, file_content)
            elif entity_type == "command":
                SyncService._update_command_from_file(entity_id, file_content)
            elif entity_type in ("hook", "rule"):
                SyncService._update_hooks_from_json(plugin_id, plugin_dir, file_content)
            else:
                log.warning("No update handler for entity type: %s", entity_type)
                return False
        except Exception:
            log.exception(
                "Error updating DB for %s %s from file %s",
                entity_type,
                entity_id,
                file_path,
            )
            return False

        # Update sync state
        update_sync_state(
            plugin_id=plugin_id,
            entity_type=entity_type,
            entity_id=entity_id,
            content_hash=new_hash,
            sync_direction="from_disk",
        )

        log.info("Synced file to DB: %s -> %s %s", file_path, entity_type, entity_id)
        return True

    @staticmethod
    def get_sync_status(plugin_id: str) -> dict:
        """Get sync overview for a plugin.

        Returns:
            Dict with entity_count, last_synced_at, error_count, watching status.
        """
        sync_states = get_sync_states_for_plugin(plugin_id)
        entity_count = len(sync_states)
        last_synced = None
        for state in sync_states:
            ts = state.get("last_synced_at")
            if ts and (last_synced is None or ts > last_synced):
                last_synced = ts

        return {
            "plugin_id": plugin_id,
            "entity_count": entity_count,
            "last_synced_at": last_synced,
            "watching": SyncService.is_watching(plugin_id),
            "entities": [
                {
                    "entity_type": s.get("entity_type"),
                    "entity_id": s.get("entity_id"),
                    "content_hash": s.get("content_hash"),
                    "sync_direction": s.get("sync_direction"),
                    "last_synced_at": s.get("last_synced_at"),
                }
                for s in sync_states
            ],
        }

    # --- Watcher management ---

    @classmethod
    def start_watching(cls, plugin_id: str, plugin_dir: str):
        """Start file watching for a plugin directory.

        Args:
            plugin_id: Plugin to watch.
            plugin_dir: Directory to watch for changes.
        """
        from .plugin_file_watcher import PluginFileWatcher

        with cls._watcher_lock:
            if plugin_id in cls._watchers:
                log.warning("Watcher already running for plugin %s", plugin_id)
                return
            watcher = PluginFileWatcher(plugin_id, plugin_dir)
            watcher.start()
            cls._watchers[plugin_id] = watcher

    @classmethod
    def stop_watching(cls, plugin_id: str):
        """Stop file watching for a plugin.

        Args:
            plugin_id: Plugin to stop watching.
        """
        with cls._watcher_lock:
            watcher = cls._watchers.pop(plugin_id, None)
            if watcher:
                watcher.stop()
            else:
                log.warning("No watcher running for plugin %s", plugin_id)

    @classmethod
    def is_watching(cls, plugin_id: str) -> bool:
        """Check if a plugin is currently being watched."""
        return plugin_id in cls._watchers

    # --- Internal helpers ---

    @staticmethod
    def _load_entity(entity_type: str, entity_id: str) -> Optional[dict]:
        """Load an entity from the DB based on type and ID."""
        try:
            if entity_type == "agent":
                return get_agent(entity_id)
            elif entity_type == "skill":
                return get_user_skill(int(entity_id))
            elif entity_type == "command":
                return get_command(int(entity_id))
            elif entity_type == "hook":
                return get_hook(int(entity_id))
            elif entity_type == "rule":
                return get_rule(int(entity_id))
        except (ValueError, TypeError):
            log.exception("Error loading %s with id %s", entity_type, entity_id)
        return None

    @staticmethod
    def _generate_entity_content(entity_type: str, entity: dict) -> Optional[str]:
        """Generate file content for a single entity."""
        if entity_type == "agent":
            return generate_agent_md(entity)
        elif entity_type == "skill":
            return generate_skill_md(entity)
        elif entity_type == "command":
            return generate_command_md(entity)
        return None

    @staticmethod
    def _entity_file_path(entity_type: str, entity: dict, plugin_dir: str) -> Optional[str]:
        """Determine the target file path for an entity."""
        base = Path(plugin_dir)
        if entity_type == "agent":
            name = _slugify(entity.get("name", "agent"))
            return str(base / "agents" / f"{name}.md")
        elif entity_type == "skill":
            name = _slugify(entity.get("skill_name", entity.get("name", "skill")))
            return str(base / "skills" / name / "SKILL.md")
        elif entity_type == "command":
            name = _slugify(entity.get("name", "command"))
            return str(base / "commands" / f"{name}.md")
        return None

    @staticmethod
    def _generate_hooks_bundle(
        plugin_id: str, plugin_dir: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Generate the aggregated hooks.json content for all hooks/rules in a plugin.

        Returns (json_content, target_path) tuple.
        """
        sync_states = get_sync_states_for_plugin(plugin_id)
        hooks = []
        rules = []

        for state in sync_states:
            etype = state.get("entity_type")
            eid = state.get("entity_id")
            if etype == "hook":
                entity = SyncService._load_entity("hook", eid)
                if entity:
                    hooks.append(entity)
            elif etype == "rule":
                entity = SyncService._load_entity("rule", eid)
                if entity:
                    rules.append(entity)

        if not hooks and not rules:
            return None, None

        hooks_config, _scripts = generate_hooks_json(hooks, rules)
        content = json.dumps(hooks_config, indent=2, ensure_ascii=False) + "\n"
        target = str(Path(plugin_dir) / "hooks" / "hooks.json")
        return content, target

    @staticmethod
    def _detect_entity_type(rel_path: str) -> Optional[str]:
        """Detect entity type from relative file path within plugin directory."""
        rel = rel_path.replace("\\", "/")

        if rel.startswith("agents/") and rel.endswith(".md"):
            return "agent"
        elif rel.startswith("skills/") and rel.endswith("SKILL.md"):
            return "skill"
        elif rel.startswith("commands/") and rel.endswith(".md"):
            return "command"
        elif rel == "hooks/hooks.json":
            return "hook"
        return None

    @staticmethod
    def _find_sync_state_by_path(
        plugin_id: str, entity_type: str, file_path: str
    ) -> Optional[dict]:
        """Find a sync_state entry matching a file path."""
        sync_states = get_sync_states_for_plugin(plugin_id)
        abs_path = str(Path(file_path).resolve())
        for state in sync_states:
            stored_path = state.get("file_path", "")
            if stored_path == file_path or str(Path(stored_path).resolve()) == abs_path:
                return state
        # Fallback: match by entity type and file name pattern
        for state in sync_states:
            if state.get("entity_type") == entity_type:
                stored = state.get("file_path", "")
                if Path(stored).name == Path(file_path).name:
                    return state
        return None

    @staticmethod
    def _update_agent_from_file(entity_id: str, file_content: str):
        """Parse agent markdown and update the agent in DB."""
        frontmatter, body = parse_yaml_frontmatter(file_content)
        update_kwargs = {}
        if body:
            update_kwargs["system_prompt"] = body
        if frontmatter.get("name"):
            update_kwargs["name"] = frontmatter["name"]
        if frontmatter.get("description"):
            update_kwargs["description"] = frontmatter["description"]
        if update_kwargs:
            update_agent(entity_id, **update_kwargs)

    @staticmethod
    def _update_skill_from_file(entity_id: str, file_content: str):
        """Parse skill markdown and update the skill in DB."""
        frontmatter, body = parse_yaml_frontmatter(file_content)
        update_kwargs = {}
        if body:
            update_kwargs["description"] = body.strip()
        if frontmatter.get("description"):
            update_kwargs["description"] = frontmatter["description"]
        if update_kwargs:
            update_user_skill(int(entity_id), **update_kwargs)

    @staticmethod
    def _update_command_from_file(entity_id: str, file_content: str):
        """Parse command markdown and update the command in DB."""
        frontmatter, body = parse_yaml_frontmatter(file_content)
        update_kwargs = {}
        if body:
            update_kwargs["content"] = body
        if frontmatter.get("description"):
            update_kwargs["description"] = frontmatter["description"]
        if frontmatter.get("parameters"):
            update_kwargs["arguments"] = json.dumps(frontmatter["parameters"])
        if update_kwargs:
            update_command(int(entity_id), **update_kwargs)

    @staticmethod
    def _update_hooks_from_json(plugin_id: str, plugin_dir: str, file_content: str):
        """Parse hooks.json and update corresponding hooks/rules in DB.

        Each hook entry in the JSON maps back to a sync_state entity.
        """
        try:
            hooks_data = json.loads(file_content)
        except json.JSONDecodeError:
            log.error("Invalid JSON in hooks.json for plugin %s", plugin_id)
            return

        hook_entries = hooks_data.get("hooks", [])
        sync_states = get_sync_states_for_plugin(plugin_id)

        # Match hook entries back to DB entities by order/description
        hook_states = [s for s in sync_states if s.get("entity_type") in ("hook", "rule")]

        for i, entry in enumerate(hook_entries):
            if i < len(hook_states):
                state = hook_states[i]
                etype = state.get("entity_type")
                eid = state.get("entity_id")
                try:
                    if etype == "hook":
                        update_kwargs = {}
                        if entry.get("event"):
                            update_kwargs["event"] = entry["event"]
                        if entry.get("description"):
                            update_kwargs["description"] = entry["description"]
                        if update_kwargs:
                            update_hook(int(eid), **update_kwargs)
                    elif etype == "rule":
                        update_kwargs = {}
                        if entry.get("description"):
                            update_kwargs["description"] = entry["description"]
                        if update_kwargs:
                            update_rule(int(eid), **update_kwargs)
                except (ValueError, TypeError):
                    log.exception("Error updating %s %s from hooks.json", etype, eid)
