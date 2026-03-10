"""Tests for execution log FTS5 search with new filters (status, date range, bot_name)."""

import pytest

from app.services.execution_search_service import ExecutionSearchService


class TestExecutionSearchFilters:
    """Verify the new filter parameters in ExecutionSearchService.search."""

    def test_search_with_status_filter(self, isolated_db):
        """search() with status filter should pass the param without error."""
        # FTS index starts empty so we just verify no exception is raised
        results = ExecutionSearchService.search(query="security", status="completed")
        assert isinstance(results, list)

    def test_search_with_date_range(self, isolated_db):
        """search() with date range should pass without error."""
        results = ExecutionSearchService.search(
            query="error",
            started_after="2026-01-01T00:00:00",
            started_before="2026-12-31T23:59:59",
        )
        assert isinstance(results, list)

    def test_search_with_bot_name_filter(self, isolated_db):
        """search() with bot_name filter should pass without error."""
        results = ExecutionSearchService.search(query="scan", bot_name="security")
        assert isinstance(results, list)

    def test_search_all_filters_combined(self, isolated_db):
        """All new filters combined should not raise an error."""
        results = ExecutionSearchService.search(
            query="auth",
            trigger_id="bot-security",
            status="failed",
            started_after="2026-01-01",
            started_before="2026-12-31",
            bot_name="security",
        )
        assert isinstance(results, list)

    def test_search_stats_returns_count(self, isolated_db):
        """get_search_stats() should return indexed_documents count."""
        stats = ExecutionSearchService.get_search_stats()
        assert "indexed_documents" in stats
        assert isinstance(stats["indexed_documents"], int)
        assert stats["indexed_documents"] >= 0

    def test_api_search_with_status_param(self, client):
        """GET /admin/execution-search?q=test&status=completed should return 200."""
        resp = client.get("/admin/execution-search?q=test&status=completed")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "results" in data
        assert "total" in data

    def test_api_search_with_date_params(self, client):
        """GET /admin/execution-search with date range params should return 200."""
        resp = client.get(
            "/admin/execution-search?q=test&started_after=2026-01-01&started_before=2026-12-31"
        )
        assert resp.status_code == 200

    def test_api_search_with_bot_name(self, client):
        """GET /admin/execution-search with bot_name param should return 200."""
        resp = client.get("/admin/execution-search?q=scan&bot_name=security")
        assert resp.status_code == 200
