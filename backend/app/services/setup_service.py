"""Bundle installation service for first-launch setup."""

import logging
import os
import subprocess
from http import HTTPStatus
from typing import Tuple

from app.models.common import error_response

from ..database import (
    create_marketplace,
    get_all_marketplaces,
    get_marketplace_plugins,
    get_setting,
    set_setting,
)
from .plugin_deploy_service import DeployService

logger = logging.getLogger(__name__)

BUNDLE_MARKETPLACE_URL = "https://github.com/ca1773130n/claude-code-plugin-marketplace"
BUNDLE_MARKETPLACE_NAME = "Claude Code Plugin Marketplace"
BUNDLE_PLUGINS = [
    {"remote_name": "harness-sync", "is_harness": True},
    {"remote_name": "grd", "is_harness": False},
]

# CLI plugins to install into each Claude Code account's config directory.
# These are installed via `claude plugins install <name>` with CLAUDE_CONFIG_DIR set.
BUNDLE_CLI_PLUGINS = [
    "superpowers",
    "feature-dev",
    "hookify",
    "pr-review-toolkit",
    "ralph-loop",
    "code-review",
    "code-simplifier",
    "commit-commands",
    "claude-md-management",
    "frontend-design",
    "security-guidance",
    "context7",
    "github",
    "playwright",
]


class SetupBundleService:
    """Service for first-launch bundle installation."""

    @staticmethod
    def bundle_install() -> Tuple[dict, int]:
        """Auto-install bundled marketplace and plugins on first launch."""
        if get_setting("bundle_installed") == "true":
            return {"status": "already_installed"}, HTTPStatus.OK

        # Find or create marketplace
        marketplace_created = False
        marketplace_id = None
        for mkt in get_all_marketplaces():
            if mkt.get("url") == BUNDLE_MARKETPLACE_URL:
                marketplace_id = mkt["id"]
                break

        if not marketplace_id:
            marketplace_id = create_marketplace(BUNDLE_MARKETPLACE_NAME, BUNDLE_MARKETPLACE_URL)
            if not marketplace_id:
                return error_response(
                    "INTERNAL_SERVER_ERROR",
                    "Failed to create marketplace",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            marketplace_created = True

        # Check already-installed plugins
        existing = {p["remote_name"] for p in get_marketplace_plugins(marketplace_id)}

        plugins_installed = []
        harness_plugin_set = False

        for plugin_spec in BUNDLE_PLUGINS:
            remote_name = plugin_spec["remote_name"]
            if remote_name in existing:
                logger.info("Bundle plugin '%s' already installed, skipping", remote_name)
                # Still need to set harness if applicable
                if plugin_spec["is_harness"]:
                    SetupBundleService._set_harness_from_existing(marketplace_id, remote_name)
                    harness_plugin_set = True
                continue

            try:
                result = DeployService.load_from_marketplace(marketplace_id, remote_name)
                plugins_installed.append(remote_name)

                if plugin_spec["is_harness"]:
                    plugin_id = result.get("plugin_id", "")
                    set_setting("harness_plugin_id", plugin_id)
                    set_setting("harness_marketplace_id", marketplace_id)
                    set_setting("harness_plugin_name", remote_name)
                    harness_plugin_set = True
            except Exception as e:
                logger.warning("Failed to install bundle plugin '%s': %s", remote_name, e)

        # Schedule CLI plugin install + proxy token refresh as background tasks.
        # (subprocess + gevent fork crashes on macOS if run inline.)
        import threading

        def _safe_install():
            try:
                SetupBundleService._install_cli_plugins_all_accounts()
            except Exception as e:
                logger.warning("Background CLI plugin install failed: %s", e)

        def _safe_refresh():
            try:
                SetupBundleService._refresh_proxy_tokens()
            except Exception as e:
                logger.warning("Background proxy token refresh failed: %s", e)

        threading.Thread(target=_safe_install, daemon=True).start()
        threading.Thread(target=_safe_refresh, daemon=True).start()

        set_setting("bundle_installed", "true")

        return {
            "status": "installed",
            "marketplace_created": marketplace_created,
            "marketplace_id": marketplace_id,
            "plugins_installed": plugins_installed,
            "harness_plugin_set": harness_plugin_set,
            "cli_plugins_scheduled": True,
        }, HTTPStatus.CREATED

    @staticmethod
    def _set_harness_from_existing(marketplace_id: str, remote_name: str) -> None:
        """Set harness settings from an already-installed marketplace plugin."""
        for p in get_marketplace_plugins(marketplace_id):
            if p["remote_name"] == remote_name:
                set_setting("harness_plugin_id", p.get("plugin_id", ""))
                set_setting("harness_marketplace_id", marketplace_id)
                set_setting("harness_plugin_name", remote_name)
                return

    @staticmethod
    def _install_cli_plugins_all_accounts() -> dict:
        """Install CLI plugins into all registered Claude Code accounts.

        For each account with a config_path, runs:
            CLAUDE_CONFIG_DIR=<config_path> claude plugins install <plugin>
        """
        from ..db.backends import get_backend_accounts

        accounts = get_backend_accounts("backend-claude")
        if not accounts:
            logger.info("No Claude accounts found — skipping CLI plugin install")
            return {"accounts": 0, "installed": []}

        results = []
        for account in accounts:
            config_path = account.get("config_path")
            if not config_path:
                logger.info(
                    "Account '%s' has no config_path — skipping CLI plugin install",
                    account.get("account_name"),
                )
                continue

            config_dir = os.path.expanduser(config_path)
            account_name = account.get("account_name", "unknown")
            installed = []

            for plugin_name in BUNDLE_CLI_PLUGINS:
                try:
                    env = {
                        **os.environ,
                        "CLAUDE_CONFIG_DIR": config_dir,
                        "OBJC_DISABLE_INITIALIZE_FORK_SAFETY": "YES",
                    }
                    result = subprocess.run(
                        ["claude", "plugins", "install", plugin_name],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        installed.append(plugin_name)
                        logger.info(
                            "Installed CLI plugin '%s' for account '%s'",
                            plugin_name, account_name,
                        )
                    else:
                        stderr = result.stderr.strip()
                        if "already installed" in stderr.lower():
                            logger.debug(
                                "CLI plugin '%s' already installed for '%s'",
                                plugin_name, account_name,
                            )
                        else:
                            logger.warning(
                                "Failed to install CLI plugin '%s' for '%s': %s",
                                plugin_name, account_name, stderr[:200],
                            )
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Timeout installing CLI plugin '%s' for '%s'",
                        plugin_name, account_name,
                    )
                except FileNotFoundError:
                    logger.warning("claude CLI not found — cannot install CLI plugins")
                    return {"accounts": 0, "error": "claude CLI not found"}
                except Exception as e:
                    logger.warning(
                        "Error installing CLI plugin '%s' for '%s': %s",
                        plugin_name, account_name, e,
                    )

            results.append({
                "account": account_name,
                "config_dir": config_dir,
                "installed": installed,
                "total": len(BUNDLE_CLI_PLUGINS),
            })

        return {"accounts": len(results), "results": results}

    @staticmethod
    def _refresh_proxy_tokens() -> None:
        """Refresh CLIProxyAPI tokens for all accounts.

        After onboarding, the user's browser has fresh OAuth cookies from the
        CLI login flows. This method triggers CLIProxyAPI login for each
        registered account to establish proxy credentials.
        """
        try:
            from ..services.cliproxy_manager import CLIProxyManager

            # First, try to start a proxy login for each Claude account
            from ..db.backends import get_backend_accounts

            for account in get_backend_accounts("backend-claude"):
                config_path = account.get("config_path")
                if not config_path:
                    continue
                try:
                    proc, auth_info = CLIProxyManager.start_login(
                        backend_type="claude",
                        config_dir=config_path,
                    )
                    # The login process runs in the background, waiting for
                    # OAuth callback. Since we can't automate the browser
                    # approval here, just log the URL for manual use.
                    url = auth_info.get("url", "")
                    if url:
                        logger.info(
                            "CLIProxyAPI login started for '%s' — approve at: %s",
                            account.get("account_name"), url[:80],
                        )
                    # Wait briefly for completion (auto-completes if cookies valid)
                    try:
                        proc.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except FileNotFoundError:
                    logger.info("cliproxyapi binary not found — skipping proxy login")
                    return
                except Exception as e:
                    logger.warning(
                        "CLIProxyAPI login failed for '%s': %s",
                        account.get("account_name"), e,
                    )

            # Then try the bulk refresh for any expired tokens
            try:
                result = CLIProxyManager.refresh_expired_tokens(timeout_per_account=45)
                refreshed = result.get("refreshed", [])
                if refreshed:
                    logger.info("CLIProxyAPI refreshed %d token(s): %s", len(refreshed), refreshed)
            except Exception as e:
                logger.warning("CLIProxyAPI token refresh failed: %s", e)
        except Exception as e:
            logger.warning("CLIProxyAPI setup failed: %s", e)
