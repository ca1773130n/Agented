"""v0.6.2: in-memory metrics registry tests."""

import pytest


@pytest.fixture(autouse=True)
def _reset_registry():
    from app_litestar.metrics import registry

    registry.reset_for_test()
    yield
    registry.reset_for_test()


class TestPathPrefix:
    def test_admin_auth(self):
        from app_litestar.metrics import _Registry

        assert _Registry._path_prefix("/admin/auth/login") == "/admin/auth"
        assert _Registry._path_prefix("/admin/auth/logout") == "/admin/auth"

    def test_admin_buckets(self):
        from app_litestar.metrics import _Registry

        assert _Registry._path_prefix("/admin/agents") == "/admin/agents"
        assert _Registry._path_prefix("/admin/projects/123") == "/admin/projects"
        assert _Registry._path_prefix("/admin/users/x/role") == "/admin/rbac"
        assert _Registry._path_prefix("/admin/something") == "/admin/other"

    def test_health(self):
        from app_litestar.metrics import _Registry

        assert _Registry._path_prefix("/health/liveness") == "/health"

    def test_unknown(self):
        from app_litestar.metrics import _Registry

        assert _Registry._path_prefix("/wat") == "other"


class TestRecordRequest:
    def test_increments_counter_and_histogram(self):
        from app_litestar.metrics import registry

        registry.record_request("GET", "/api/agents", 200, 42.5)
        registry.record_request("GET", "/api/agents", 200, 13.0)
        registry.record_request("GET", "/api/agents", 500, 1234.0)
        text = registry.render_text()
        assert (
            'agented_http_requests_total{method="GET",path_prefix="/api/other",status="200"} 2'
            in text
        )
        assert (
            'agented_http_requests_total{method="GET",path_prefix="/api/other",status="500"} 1'
            in text
        )
        # Histogram has buckets + _sum + _count.
        assert "agented_http_request_duration_ms_bucket" in text
        assert "agented_http_request_duration_ms_sum" in text
        assert "agented_http_request_duration_ms_count" in text

    def test_rate_limit_denial_counter(self):
        from app_litestar.metrics import registry

        registry.record_rate_limit_denied("/api/auth/login", "ip")
        registry.record_rate_limit_denied("/api/auth/login", "ip")
        text = registry.render_text()
        assert 'agented_rate_limit_denied_total{path_prefix="/api/auth",key_kind="ip"} 2' in text


class TestRenderText:
    def test_emits_help_and_type_lines(self):
        from app_litestar.metrics import registry

        registry.record_request("GET", "/health/liveness", 200, 1.0)
        text = registry.render_text()
        assert "# HELP agented_http_requests_total" in text
        assert "# TYPE agented_http_requests_total counter" in text
        assert "# TYPE agented_http_request_duration_ms histogram" in text

    def test_handles_no_data_gracefully(self):
        from app_litestar.metrics import registry

        text = registry.render_text()
        assert "# HELP agented_http_requests_total" in text
        # No bucket/sum/count lines for histograms with no data.
        assert "agented_http_request_duration_ms_bucket" not in text

    def test_session_event_label_escaping(self, isolated_db):
        """Codex round-1 I1: session_event labels with `\\` + `"` must
        escape in correct order (backslash first, then quote)."""
        from app.database import get_connection
        from app_litestar.metrics import registry

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO session_events (session_id, user_id, event_type) VALUES ('s', 'u', ?)",
                ('back\\slash"quote',),
            )
            conn.commit()
        text = registry.render_text()
        # Original `back\slash"quote` should render as
        # `back\\slash\"quote` in the label value.
        assert 'event_type="back\\\\slash\\"quote"' in text


class TestHistogram:
    def test_buckets_cumulative(self):
        from app_litestar.metrics import _Histogram

        h = _Histogram(buckets=(10.0, 50.0, 100.0))
        h.observe(5.0)  # le 10
        h.observe(25.0)  # le 50, le 100
        h.observe(150.0)  # le +Inf only
        counts, _sum, total, _ = h.snapshot()
        assert counts == [1, 2, 2, 3]  # cumulative — 1, 1+1, 1+1+0, all 3
        assert total == 3
        assert _sum == 180.0
