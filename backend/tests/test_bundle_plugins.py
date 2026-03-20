from app.services.setup_service import BUNDLE_PLUGINS
from app.services.harness_plugin_installer import BUNDLE_PLUGINS as CLI_BUNDLE_PLUGINS


def test_everything_claude_code_in_setup_bundle():
    names = [p["remote_name"] for p in BUNDLE_PLUGINS]
    assert "affaan-m/everything-claude-code" in names


def test_everything_claude_code_in_cli_bundle():
    assert "everything-claude-code" in CLI_BUNDLE_PLUGINS
