"""v0.5.13: healthcheck CLI tests."""

import urllib.error
from unittest.mock import MagicMock, patch


def _ok_response(status: int = 200):
    resp = MagicMock()
    resp.status = status
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


class TestProbe:
    def test_returns_ok_on_200(self):
        from scripts.healthcheck import _probe

        with patch("scripts.healthcheck.urllib.request.urlopen", return_value=_ok_response(200)):
            ok, detail = _probe("http://x/health")
        assert ok is True
        assert detail == "200"

    def test_returns_red_on_non_200(self):
        from scripts.healthcheck import _probe

        with patch("scripts.healthcheck.urllib.request.urlopen", return_value=_ok_response(503)):
            ok, detail = _probe("http://x/health")
        assert ok is False
        assert "503" in detail

    def test_returns_red_on_url_error(self):
        from scripts.healthcheck import _probe

        with patch(
            "scripts.healthcheck.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            ok, detail = _probe("http://x/health")
        assert ok is False
        assert "unreachable" in detail


class TestRun:
    def test_all_green_when_three_probes_ok(self):
        from scripts.healthcheck import run

        with patch("scripts.healthcheck.urllib.request.urlopen", return_value=_ok_response(200)):
            rc, results = run()
        assert rc == 0
        assert all(p["ok"] for p in results.values())
        assert set(results) == {"backend.liveness", "backend.readiness", "sidecar.health"}

    def test_red_when_any_probe_fails(self):
        from scripts.healthcheck import run

        # First two ok, third fails.
        responses = [_ok_response(200), _ok_response(200), urllib.error.URLError("nope")]

        def fake_urlopen(url, timeout=None):
            r = responses.pop(0)
            if isinstance(r, urllib.error.URLError):
                raise r
            return r

        with patch("scripts.healthcheck.urllib.request.urlopen", side_effect=fake_urlopen):
            rc, results = run()
        assert rc == 1
        assert results["sidecar.health"]["ok"] is False


class TestCLI:
    def test_main_exits_0_on_all_green(self, capsys):
        from scripts.healthcheck import main

        with patch("scripts.healthcheck.urllib.request.urlopen", return_value=_ok_response(200)):
            rc = main([])
        assert rc == 0
        captured = capsys.readouterr()
        assert "green" in captured.out

    def test_main_exits_1_with_structured_stderr(self, capsys):
        from scripts.healthcheck import main

        with patch(
            "scripts.healthcheck.urllib.request.urlopen",
            side_effect=urllib.error.URLError("down"),
        ):
            rc = main([])
        assert rc == 1
        captured = capsys.readouterr()
        assert "red" in captured.err
        assert "backend.liveness" in captured.err


class TestLivenessOnly:
    def test_liveness_only_skips_readiness_and_sidecar(self, capsys):
        """Container HEALTHCHECK uses --liveness-only because the sidecar
        is a separate container in compose. Probing localhost:20001 from
        inside the backend container would always fail."""
        from scripts.healthcheck import run

        with patch(
            "scripts.healthcheck.urllib.request.urlopen", return_value=_ok_response(200)
        ) as up:
            rc, results = run(liveness_only=True)
        assert rc == 0
        assert set(results) == {"backend.liveness"}
        assert up.call_count == 1

    def test_liveness_only_via_CLI_flag(self, capsys):
        from scripts.healthcheck import main

        with patch("scripts.healthcheck.urllib.request.urlopen", return_value=_ok_response(200)):
            rc = main(["--liveness-only"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "backend.liveness" in captured.out
        assert "sidecar.health" not in captured.out
