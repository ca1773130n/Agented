"""Regression: MCP test_connection blocks link-local/metadata SSRF targets,
but still allows legitimate localhost/LAN MCP servers (05-integrations M3)."""

from app.services.mcp_sync_service import McpSyncService as M


def test_blocks_cloud_metadata_link_local():
    reason = M._unsafe_http_target("http://169.254.169.254/latest/meta-data/")
    assert reason is not None
    assert "169.254.169.254" in reason


def test_blocks_non_http_scheme():
    assert M._unsafe_http_target("file:///etc/passwd") is not None
    assert M._unsafe_http_target("gopher://x/") is not None


def test_allows_loopback_and_private():
    # MCP servers legitimately run locally / on the LAN.
    assert M._unsafe_http_target("http://127.0.0.1:9000/") is None
    assert M._unsafe_http_target("http://[::1]:9000/") is None
    assert M._unsafe_http_target("http://10.0.0.5:8080/") is None
