"""Tests for /health API routes."""


class TestLiveness:
    def test_liveness(self, client):
        """GET /health/liveness returns 200."""
        resp = client.get("/health/liveness")
        assert resp.status_code == 200


class TestReadiness:
    def test_readiness_unauthenticated(self, client):
        """GET /health/readiness without API key returns minimal response."""
        resp = client.get("/health/readiness")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ok"
        assert "timestamp" in body
        # Unauthenticated should NOT have components
        assert "components" not in body

    def test_readiness_authenticated(self, client, monkeypatch):
        """GET /health/readiness with valid API key returns full details."""
        monkeypatch.setenv("AGENTED_API_KEY", "test-secret-key")
        resp = client.get("/health/readiness", headers={"X-API-Key": "test-secret-key"})
        assert resp.status_code in (200, 503)  # 503 if degraded
        body = resp.get_json()
        assert "status" in body
        assert "components" in body
        assert "database" in body["components"]

    def test_readiness_wrong_api_key(self, client, monkeypatch):
        """GET /health/readiness with wrong API key returns minimal response."""
        monkeypatch.setenv("AGENTED_API_KEY", "correct-key")
        resp = client.get("/health/readiness", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 200
        body = resp.get_json()
        # Wrong key should get minimal response (no components)
        assert "components" not in body
