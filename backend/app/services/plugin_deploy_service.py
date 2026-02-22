"""Plugin deployment service for marketplace git operations.

Handles deploying exported plugins to marketplace git repos and
loading plugins from marketplace repos into Hive entities.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time

from app.database import (
    add_marketplace_plugin,
    get_marketplace,
    get_marketplace_plugins,
    get_plugin,
    get_plugin_exports_for_plugin,
    update_plugin_export,
)

log = logging.getLogger(__name__)

# In-memory cache for marketplace discovery results
_marketplace_cache: dict = {}  # {marketplace_id: {"data": {...}, "fetched_at": float}}
_CACHE_TTL = 300  # 5 minutes


class DeployService:
    """Service for deploying plugins to marketplaces and loading from marketplaces."""

    @staticmethod
    def deploy_to_marketplace(plugin_id: str, marketplace_id: str, version: str = "1.0.0") -> dict:
        """Deploy an exported plugin to a marketplace git repository.

        Args:
            plugin_id: ID of the plugin to deploy.
            marketplace_id: ID of the target marketplace.
            version: Version string for the deployment.

        Returns:
            Dict with message, marketplace_url, and plugin_name.

        Raises:
            ValueError: If marketplace, plugin, or export not found.
            RuntimeError: If git operations fail.
        """
        # 1. Load marketplace
        marketplace = get_marketplace(marketplace_id)
        if not marketplace:
            raise ValueError(f"Marketplace not found: {marketplace_id}")

        marketplace_url = marketplace.get("url", "")
        if not marketplace_url:
            raise ValueError(f"Marketplace has no URL configured: {marketplace_id}")

        # 2. Load plugin
        plugin = get_plugin(plugin_id)
        if not plugin:
            raise ValueError(f"Plugin not found: {plugin_id}")

        plugin_name = DeployService._slugify(plugin.get("name", "unnamed"))

        # 3. Find latest export
        exports = get_plugin_exports_for_plugin(plugin_id)
        if not exports:
            raise ValueError("Plugin must be exported before deploying")

        latest_export = exports[0]  # Already ordered by created_at DESC
        export_path = latest_export.get("export_path")
        if not export_path or not os.path.isdir(export_path):
            raise ValueError(
                f"Export path not found or invalid: {export_path}. "
                "Please re-export the plugin before deploying."
            )

        export_id = latest_export.get("id")

        # 4-9. Clone, copy, commit, push
        with tempfile.TemporaryDirectory(prefix="hive-deploy-") as temp_dir:
            # 5. Clone marketplace repo
            try:
                subprocess.run(
                    ["git", "clone", marketplace_url, temp_dir],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                log.info("Cloned marketplace repo: %s", marketplace_url)
            except subprocess.CalledProcessError as e:
                stderr = e.stderr or ""
                raise RuntimeError(f"Failed to clone marketplace repo: {stderr.strip()}") from e
            except subprocess.TimeoutExpired:
                raise RuntimeError(
                    "Git clone timed out after 60 seconds. "
                    "Check the marketplace URL and network connectivity."
                )

            # 6. Determine plugin directory in marketplace
            plugin_dir = os.path.join(temp_dir, "plugins", plugin_name)

            # 7. Copy exported plugin files
            shutil.copytree(export_path, plugin_dir, dirs_exist_ok=True)
            log.info("Copied plugin files to %s", plugin_dir)

            # 8. Update marketplace.json (check .claude-plugin/ first, then root)
            claude_plugin_path = os.path.join(temp_dir, ".claude-plugin", "marketplace.json")
            root_path = os.path.join(temp_dir, "marketplace.json")
            if os.path.exists(claude_plugin_path):
                marketplace_json_path = claude_plugin_path
            elif os.path.exists(root_path):
                marketplace_json_path = root_path
            else:
                marketplace_json_path = claude_plugin_path
                os.makedirs(os.path.dirname(marketplace_json_path), exist_ok=True)
            marketplace_data = {"plugins": []}
            if os.path.exists(marketplace_json_path):
                try:
                    with open(marketplace_json_path, "r", encoding="utf-8") as f:
                        marketplace_data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    log.warning("Could not parse marketplace.json, creating new one")
                    marketplace_data = {"plugins": []}

            # Ensure plugins list exists
            if "plugins" not in marketplace_data:
                marketplace_data["plugins"] = []

            # Add or update plugin entry
            plugin_entry = {
                "name": plugin_name,
                "source": f"./plugins/{plugin_name}",
                "description": plugin.get("description", ""),
                "version": version,
            }

            # Update existing entry or append new one
            existing_idx = None
            for idx, p in enumerate(marketplace_data["plugins"]):
                if p.get("name") == plugin_name:
                    existing_idx = idx
                    break

            if existing_idx is not None:
                marketplace_data["plugins"][existing_idx] = plugin_entry
            else:
                marketplace_data["plugins"].append(plugin_entry)

            with open(marketplace_json_path, "w", encoding="utf-8") as f:
                json.dump(marketplace_data, f, indent=2, ensure_ascii=False)
                f.write("\n")

            # 9. Git add, commit, push
            try:
                subprocess.run(
                    ["git", "add", "."],
                    cwd=temp_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", f"Deploy {plugin_name} v{version}"],
                    cwd=temp_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    ["git", "push"],
                    cwd=temp_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                log.info(
                    "Pushed %s v%s to marketplace %s",
                    plugin_name,
                    version,
                    marketplace_url,
                )
            except subprocess.CalledProcessError as e:
                stderr = e.stderr or ""
                if "auth" in stderr.lower() or "permission" in stderr.lower():
                    raise RuntimeError(
                        f"Git push failed (authentication): {stderr.strip()}. "
                        "Check your system git credentials for the marketplace repo."
                    ) from e
                raise RuntimeError(f"Git push failed: {stderr.strip()}") from e
            except subprocess.TimeoutExpired:
                raise RuntimeError(
                    "Git push timed out after 60 seconds. "
                    "Check network connectivity and repository access."
                )

        # 10. Update export status
        if export_id:
            update_plugin_export(
                export_id,
                status="deployed",
            )

        # 11. Return result
        return {
            "message": "Plugin deployed",
            "marketplace_url": marketplace_url,
            "plugin_name": plugin_name,
        }

    @staticmethod
    def load_from_marketplace(marketplace_id: str, remote_plugin_name: str) -> dict:
        """Load a plugin from a marketplace into Hive entities.

        Args:
            marketplace_id: ID of the marketplace to load from.
            remote_plugin_name: Name of the plugin in the marketplace.

        Returns:
            Dict with import results (plugin_id, entity counts, etc.).

        Raises:
            ValueError: If marketplace not found or plugin not in marketplace.
            RuntimeError: If git operations fail.
        """
        # Lazy import to avoid circular imports
        from app.services.plugin_import_service import ImportService

        # 1. Load marketplace
        marketplace = get_marketplace(marketplace_id)
        if not marketplace:
            raise ValueError(f"Marketplace not found: {marketplace_id}")

        marketplace_url = marketplace.get("url", "")
        if not marketplace_url:
            raise ValueError(f"Marketplace has no URL configured: {marketplace_id}")

        # 2. Clone marketplace repo
        with tempfile.TemporaryDirectory(prefix="hive-load-") as temp_dir:
            try:
                subprocess.run(
                    ["git", "clone", marketplace_url, temp_dir],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                log.info("Cloned marketplace repo for loading: %s", marketplace_url)
            except subprocess.CalledProcessError as e:
                stderr = e.stderr or ""
                raise RuntimeError(f"Failed to clone marketplace repo: {stderr.strip()}") from e
            except subprocess.TimeoutExpired:
                raise RuntimeError(
                    "Git clone timed out after 60 seconds. "
                    "Check the marketplace URL and network connectivity."
                )

            # 2b. Initialize git submodules (plugins may be submodules)
            try:
                subprocess.run(
                    ["git", "submodule", "update", "--init", "--recursive"],
                    cwd=temp_dir,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except subprocess.TimeoutExpired:
                log.warning("Git submodule init timed out for %s", marketplace_url)

            # 3. Read marketplace.json to find plugin (check .claude-plugin/ first, then root)
            claude_plugin_path = os.path.join(temp_dir, ".claude-plugin", "marketplace.json")
            root_path = os.path.join(temp_dir, "marketplace.json")
            if os.path.exists(claude_plugin_path):
                marketplace_json_path = claude_plugin_path
            elif os.path.exists(root_path):
                marketplace_json_path = root_path
            else:
                raise ValueError(
                    "Marketplace repo has no marketplace.json. "
                    "The marketplace may be empty or misconfigured."
                )

            try:
                with open(marketplace_json_path, "r", encoding="utf-8") as f:
                    marketplace_data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                raise ValueError(f"Could not parse marketplace.json: {e}") from e

            plugins_list = marketplace_data.get("plugins", [])
            plugin_entry = None
            for p in plugins_list:
                if p.get("name") == remote_plugin_name:
                    plugin_entry = p
                    break

            if not plugin_entry:
                available = [p.get("name", "?") for p in plugins_list]
                raise ValueError(
                    f"Plugin '{remote_plugin_name}' not found in marketplace. "
                    f"Available plugins: {', '.join(available) if available else 'none'}"
                )

            # 4. Resolve plugin directory
            source_obj = plugin_entry.get("source", f"./plugins/{remote_plugin_name}")
            plugin_dir = None

            # Handle URL-sourced plugins: clone from external URL
            if isinstance(source_obj, dict) and source_obj.get("source") == "url":
                plugin_url = source_obj.get("url")
                if plugin_url:
                    url_clone_dir = os.path.join(temp_dir, "_url_plugin")
                    try:
                        subprocess.run(
                            ["git", "clone", "--depth", "1", plugin_url, url_clone_dir],
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=60,
                        )
                        plugin_dir = url_clone_dir
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                        log.warning("Failed to clone plugin URL %s: %s", plugin_url, e)

            # Fallback: resolve as local path within marketplace repo
            if not plugin_dir or not os.path.isdir(plugin_dir):
                if isinstance(source_obj, dict):
                    source_path = source_obj.get("path") or f"./plugins/{remote_plugin_name}"
                elif isinstance(source_obj, str):
                    source_path = source_obj
                else:
                    source_path = f"./plugins/{remote_plugin_name}"
                plugin_dir = os.path.normpath(os.path.join(temp_dir, source_path))

            if not os.path.isdir(plugin_dir):
                raise ValueError(
                    f"Plugin directory not found in marketplace repo: {remote_plugin_name}"
                )

            # 5. Import using ImportService
            result = ImportService.import_plugin_directory(
                plugin_dir, plugin_name=remote_plugin_name
            )

            # 6. Record marketplace-plugin relationship
            plugin_id = result.get("plugin_id")
            if plugin_id:
                add_marketplace_plugin(
                    marketplace_id=marketplace_id,
                    remote_name=remote_plugin_name,
                    plugin_id=plugin_id,
                    version=plugin_entry.get("version"),
                )

            # 7. Return import result
            return result

    @staticmethod
    def discover_available_plugins(marketplace_id: str) -> dict:
        """Discover all available plugins from a marketplace repo."""
        marketplace = get_marketplace(marketplace_id)
        if not marketplace:
            raise ValueError(f"Marketplace not found: {marketplace_id}")
        url = marketplace.get("url", "")
        if not url:
            raise ValueError("Marketplace has no URL configured")

        with tempfile.TemporaryDirectory(prefix="hive-discover-") as temp_dir:
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", url, temp_dir],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except subprocess.CalledProcessError as e:
                stderr = e.stderr or ""
                raise RuntimeError(f"Failed to clone marketplace repo: {stderr.strip()}") from e
            except subprocess.TimeoutExpired:
                raise RuntimeError("Git clone timed out after 60 seconds.")

            claude_path = os.path.join(temp_dir, ".claude-plugin", "marketplace.json")
            root_path = os.path.join(temp_dir, "marketplace.json")
            if os.path.exists(claude_path):
                mj_path = claude_path
            elif os.path.exists(root_path):
                mj_path = root_path
            else:
                return {"plugins": [], "total": 0}

            try:
                with open(mj_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                raise ValueError(f"Could not parse marketplace.json: {e}") from e

            available = data.get("plugins", [])
            for p in available:
                if not isinstance(p.get("name"), str):
                    p["name"] = str(p.get("name", "?"))
            installed_names = {p["remote_name"] for p in get_marketplace_plugins(marketplace_id)}
            for p in available:
                p["installed"] = p.get("name", "") in installed_names
            return {"plugins": available, "total": len(available)}

    @classmethod
    def discover_available_plugins_cached(cls, marketplace_id: str) -> dict:
        """Discover available plugins with in-memory TTL caching.

        Returns cached result if fresh (within _CACHE_TTL seconds).
        On error, returns stale cache if available; otherwise re-raises.
        """
        global _marketplace_cache

        # Check cache
        entry = _marketplace_cache.get(marketplace_id)
        if entry and (time.time() - entry["fetched_at"] < _CACHE_TTL):
            return entry["data"]

        # Fetch fresh data
        try:
            result = cls.discover_available_plugins(marketplace_id)
        except Exception:
            # Graceful degradation: return stale cache if available
            if entry:
                log.warning(
                    "Failed to refresh marketplace %s, returning stale cache", marketplace_id
                )
                return entry["data"]
            raise

        # Store in cache
        _marketplace_cache[marketplace_id] = {
            "data": result,
            "fetched_at": time.time(),
        }
        return result

    @classmethod
    def clear_marketplace_cache(cls, marketplace_id: str = None) -> None:
        """Clear marketplace discovery cache.

        Args:
            marketplace_id: If given, clear only that entry. If None, clear all.
        """
        global _marketplace_cache
        if marketplace_id:
            _marketplace_cache.pop(marketplace_id, None)
        else:
            _marketplace_cache.clear()

    @staticmethod
    def test_connection(marketplace_id: str) -> dict:
        """Test connectivity to a marketplace git repository.

        Args:
            marketplace_id: ID of the marketplace to test.

        Returns:
            Dict with connected (bool) and message (str).
        """
        marketplace = get_marketplace(marketplace_id)
        if not marketplace:
            return {"connected": False, "message": f"Marketplace not found: {marketplace_id}"}

        marketplace_url = marketplace.get("url", "")
        if not marketplace_url:
            return {"connected": False, "message": "Marketplace has no URL configured"}

        try:
            result = subprocess.run(
                ["git", "ls-remote", marketplace_url],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return {
                    "connected": True,
                    "message": f"Successfully connected to {marketplace_url}",
                }
            else:
                stderr = result.stderr or ""
                return {
                    "connected": False,
                    "message": f"Connection failed: {stderr.strip()}",
                }
        except subprocess.TimeoutExpired:
            return {
                "connected": False,
                "message": "Connection timed out after 10 seconds",
            }
        except Exception as e:
            return {
                "connected": False,
                "message": f"Connection error: {str(e)}",
            }

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a name to kebab-case suitable for directory names."""
        slug = name.lower().strip()
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-")
        return slug or "unnamed"
