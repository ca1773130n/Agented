"""Tests for marketplace search API and caching."""

import time
from unittest.mock import patch

import pytest

# Sample marketplace discovery data
SAMPLE_PLUGINS = {
    "plugins": [
        {
            "name": "code-review",
            "description": "Automated code review plugin",
            "version": "1.0.0",
            "source": "./plugins/code-review",
            "installed": False,
        },
        {
            "name": "security-scanner",
            "description": "Security vulnerability scanner",
            "version": "2.1.0",
            "source": "./plugins/security-scanner",
            "installed": False,
        },
        {
            "name": "deploy-helper",
            "description": "Deployment automation helper",
            "version": "0.5.0",
            "source": "./plugins/deploy-helper",
            "installed": True,
        },
    ],
    "skills": [
        {
            "name": "test-runner",
            "description": "Run tests automatically",
            "version": "1.0.0",
        },
        {
            "name": "doc-generator",
            "description": "Generate documentation from code",
            "version": "1.2.0",
        },
    ],
    "total": 3,
}


@pytest.fixture
def marketplace_in_db(client):
    """Create a marketplace in the database and return its ID."""
    response = client.post(
        "/admin/marketplaces/",
        json={
            "name": "Test Marketplace",
            "url": "https://github.com/test/marketplace",
            "type": "git",
        },
    )
    data = response.get_json()
    return data["marketplace"]["id"]


class TestMarketplaceSearch:
    """Tests for GET /admin/marketplaces/search endpoint."""

    def test_search_returns_empty_when_no_marketplaces(self, client):
        """Search with no registered marketplaces returns empty results."""
        response = client.get("/admin/marketplaces/search?q=test")
        assert response.status_code == 200
        data = response.get_json()
        assert data["results"] == []
        assert data["total"] == 0

    @patch("app.services.plugin_deploy_service.DeployService.discover_available_plugins")
    def test_search_filters_by_query(self, mock_discover, client, marketplace_in_db):
        """Search filters results by name substring."""
        mock_discover.return_value = SAMPLE_PLUGINS

        response = client.get("/admin/marketplaces/search?q=security")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "security-scanner"

    @patch("app.services.plugin_deploy_service.DeployService.discover_available_plugins")
    def test_search_filters_by_description(self, mock_discover, client, marketplace_in_db):
        """Search matches against description text."""
        mock_discover.return_value = SAMPLE_PLUGINS

        response = client.get("/admin/marketplaces/search?q=automation")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total"] == 1
        assert data["results"][0]["name"] == "deploy-helper"

    @patch("app.services.plugin_deploy_service.DeployService.discover_available_plugins")
    def test_search_returns_all_when_no_query(self, mock_discover, client, marketplace_in_db):
        """Empty query returns all discovered plugins."""
        mock_discover.return_value = SAMPLE_PLUGINS

        response = client.get("/admin/marketplaces/search?q=")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total"] == 3  # All plugins
        names = [r["name"] for r in data["results"]]
        assert "code-review" in names
        assert "security-scanner" in names
        assert "deploy-helper" in names

    @patch("app.services.plugin_deploy_service.DeployService.discover_available_plugins")
    def test_search_type_skill(self, mock_discover, client, marketplace_in_db):
        """type=skill searches the skills array in marketplace data."""
        mock_discover.return_value = SAMPLE_PLUGINS

        response = client.get("/admin/marketplaces/search?q=&type=skill")
        assert response.status_code == 200
        data = response.get_json()
        assert data["type"] == "skill"
        assert data["total"] == 2
        names = [r["name"] for r in data["results"]]
        assert "test-runner" in names
        assert "doc-generator" in names

    @patch("app.services.plugin_deploy_service.DeployService.discover_available_plugins")
    def test_cache_returns_stale_on_error(self, mock_discover, client, marketplace_in_db):
        """Cached data is returned when discover raises an exception on refresh."""
        from app.services.plugin_deploy_service import (
            _CACHE_TTL,
            DeployService,
            _marketplace_cache,
        )

        # Clear any existing cache
        DeployService.clear_marketplace_cache()

        # First call succeeds and populates cache
        mock_discover.return_value = SAMPLE_PLUGINS
        response = client.get("/admin/marketplaces/search?q=")
        assert response.status_code == 200
        assert response.get_json()["total"] == 3

        # Expire the cache by backdating fetched_at
        for key in _marketplace_cache:
            _marketplace_cache[key]["fetched_at"] = time.time() - _CACHE_TTL - 10

        # Second call fails - should return stale cache
        mock_discover.side_effect = RuntimeError("Git clone failed")
        response = client.get("/admin/marketplaces/search?q=")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total"] == 3  # Stale cache returned

        # Cleanup
        DeployService.clear_marketplace_cache()

    def test_cache_clear(self, client):
        """clear_marketplace_cache invalidates the cache."""
        from app.services.plugin_deploy_service import (
            DeployService,
            _marketplace_cache,
        )

        # Manually populate cache
        _marketplace_cache["test-id"] = {
            "data": {"plugins": [], "total": 0},
            "fetched_at": time.time(),
        }
        assert "test-id" in _marketplace_cache

        # Clear specific entry
        DeployService.clear_marketplace_cache("test-id")
        assert "test-id" not in _marketplace_cache

        # Populate again and clear all
        _marketplace_cache["a"] = {"data": {}, "fetched_at": time.time()}
        _marketplace_cache["b"] = {"data": {}, "fetched_at": time.time()}
        DeployService.clear_marketplace_cache()
        assert len(_marketplace_cache) == 0

    @patch("app.services.plugin_deploy_service.DeployService.discover_available_plugins")
    def test_search_includes_marketplace_attribution(
        self, mock_discover, client, marketplace_in_db
    ):
        """Results include marketplace_id and marketplace_name."""
        mock_discover.return_value = SAMPLE_PLUGINS

        response = client.get("/admin/marketplaces/search?q=code-review")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total"] == 1
        result = data["results"][0]
        assert result["marketplace_id"] == marketplace_in_db
        assert result["marketplace_name"] == "Test Marketplace"


class TestMarketplaceCacheRefresh:
    """Tests for POST /admin/marketplaces/search/refresh endpoint."""

    def test_refresh_clears_cache(self, client):
        """POST /admin/marketplaces/search/refresh clears the discovery cache."""
        from app.services.plugin_deploy_service import _marketplace_cache

        # Populate cache
        _marketplace_cache["some-id"] = {
            "data": {"plugins": []},
            "fetched_at": time.time(),
        }

        response = client.post("/admin/marketplaces/search/refresh")
        assert response.status_code == 200
        data = response.get_json()
        assert data["message"] == "Marketplace cache cleared"
        assert len(_marketplace_cache) == 0
