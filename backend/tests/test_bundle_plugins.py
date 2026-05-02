from app.services.harness_plugin_installer import BUNDLE_PLUGINS as CLI_BUNDLE_PLUGINS


def test_everything_claude_code_in_cli_bundle():
    assert "everything-claude-code" in CLI_BUNDLE_PLUGINS
