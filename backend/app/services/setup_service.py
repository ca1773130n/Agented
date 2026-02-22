"""Bundle installation service for first-launch setup."""

import logging
from http import HTTPStatus
from typing import Tuple

from ..database import (
    add_marketplace,
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
    {"remote_name": "HarnessSync", "is_harness": True},
    {"remote_name": "grd", "is_harness": False},
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
            marketplace_id = add_marketplace(BUNDLE_MARKETPLACE_NAME, BUNDLE_MARKETPLACE_URL)
            if not marketplace_id:
                return {"error": "Failed to create marketplace"}, HTTPStatus.INTERNAL_SERVER_ERROR
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

            result = DeployService.load_from_marketplace(marketplace_id, remote_name)
            plugins_installed.append(remote_name)

            if plugin_spec["is_harness"]:
                plugin_id = result.get("plugin_id", "")
                set_setting("harness_plugin_id", plugin_id)
                set_setting("harness_marketplace_id", marketplace_id)
                set_setting("harness_plugin_name", remote_name)
                harness_plugin_set = True

        set_setting("bundle_installed", "true")

        return {
            "status": "installed",
            "marketplace_created": marketplace_created,
            "marketplace_id": marketplace_id,
            "plugins_installed": plugins_installed,
            "harness_plugin_set": harness_plugin_set,
        }, HTTPStatus.CREATED

    @staticmethod
    def _set_harness_from_existing(marketplace_id: str, remote_name: str):
        """Set harness settings from an already-installed marketplace plugin."""
        for p in get_marketplace_plugins(marketplace_id):
            if p["remote_name"] == remote_name:
                set_setting("harness_plugin_id", p.get("plugin_id", ""))
                set_setting("harness_marketplace_id", marketplace_id)
                set_setting("harness_plugin_name", remote_name)
                return
