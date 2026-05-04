"""v0.6.0: profile.py CLI tests."""
import json
from unittest.mock import patch

import pytest


class TestPercentile:
    def test_percentile_at_boundaries(self):
        from scripts.profile import _percentile
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(values, 0) == 1.0
        assert _percentile(values, 50) == 3.0
        assert _percentile(values, 100) == 5.0

    def test_percentile_empty_returns_0(self):
        from scripts.profile import _percentile
        assert _percentile([], 50) == 0.0


class TestProfileEndpoint:
    def test_aggregates_min_p50_p95_max(self):
        from scripts.profile import profile_endpoint
        # Simulate 20 requests with predictable durations: 1..20 ms.
        durations = list(range(1, 21))

        def fake_request(url, *, timeout, headers):
            ms = durations.pop(0)
            return 200, float(ms), float(ms / 2)

        with patch("scripts.profile._request", side_effect=fake_request):
            entry = profile_endpoint(
                "http://x", "/health", n=20, timeout=5.0, headers={},
            )
        assert entry["n"] == 20
        assert entry["ok_count"] == 20
        assert entry["client_total_ms"]["min"] == 1.0
        assert entry["client_total_ms"]["max"] == 20.0
        # Status histogram.
        assert entry["status_codes"][200] == 20


class TestCLI:
    def test_main_emits_json_summary(self, capsys):
        from scripts import profile as profile_module

        def fake_request(url, *, timeout, headers):
            return 200, 5.0, 2.0

        with patch.object(profile_module, "_request", side_effect=fake_request):
            rc = profile_module.main([
                "--base", "http://test", "--requests", "5",
                "--endpoints", "/health/liveness",
            ])
        assert rc == 0
        out = capsys.readouterr().out
        summary = json.loads(out)
        assert summary["base"] == "http://test"
        assert len(summary["endpoints"]) == 1
        assert summary["endpoints"][0]["n"] == 5

    def test_main_exits_1_on_unreachable_server(self, capsys):
        from scripts import profile as profile_module
        import urllib.error

        def fake_request(url, *, timeout, headers):
            raise urllib.error.URLError("connection refused")

        with patch.object(profile_module, "_request", side_effect=fake_request):
            rc = profile_module.main([
                "--base", "http://nowhere", "--requests", "5",
                "--endpoints", "/health/liveness",
            ])
        assert rc == 1
