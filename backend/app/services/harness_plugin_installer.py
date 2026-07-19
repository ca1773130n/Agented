"""Install harness plugins into a Claude account's config directory via CLI."""

import logging
import os
import subprocess

logger = logging.getLogger(__name__)

MARKETPLACE_REPO = "ca1773130n/claude-code-plugin-marketplace"
BUNDLE_PLUGINS = ["HarnessSync", "grd", "everything-claude-code"]


class HarnessPluginInstaller:
    """Ensures custom marketplace and bundle plugins are installed in a Claude config dir."""

    @classmethod
    def ensure_plugins_installed(cls, config_path: str) -> dict:
        """Ensure custom marketplace + bundle plugins are installed in config dir.

        [04.H4] Returns ``{"installed": [...], "failed": [...]}`` and inspects
        the ``claude plugin install`` exit code for each plugin — a non-zero
        exit previously went unnoticed, leaving provisioning silently broken.
        """
        expanded = os.path.expanduser(config_path)
        from app import config

        # NO_LLM_KEYS: strip server-baked inference keys from the claude subprocess
        # env (flag-gated no-op when unset).
        env = config.subprocess_env({**os.environ, "CLAUDE_CONFIG_DIR": expanded})

        # Step 1: Add marketplace (idempotent — if already added, claude handles it)
        result = subprocess.run(
            ["claude", "plugin", "marketplace", "add", MARKETPLACE_REPO],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("Marketplace add returned %d: %s", result.returncode, result.stderr)

        # Step 2: List installed plugins to check what's already there
        result = subprocess.run(
            ["claude", "plugin", "list"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        installed_output = result.stdout if result.returncode == 0 else ""

        # Step 3: Install each missing plugin
        installed: list[str] = []
        failed: list[str] = []
        for plugin_name in BUNDLE_PLUGINS:
            if plugin_name.lower() in installed_output.lower():
                logger.debug("Plugin %s already installed in %s", plugin_name, expanded)
                installed.append(plugin_name)
                continue
            logger.info("Installing plugin %s into %s", plugin_name, expanded)
            res = subprocess.run(
                ["claude", "plugin", "install", plugin_name],
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            # [04.H4] Inspect the exit code; log stderr on failure.
            if res.returncode != 0:
                logger.warning(
                    "Plugin install %s failed (exit %d): %s",
                    plugin_name,
                    res.returncode,
                    (res.stderr or "").strip()[:500],
                )
                failed.append(plugin_name)
            else:
                installed.append(plugin_name)

        return {"installed": installed, "failed": failed}
