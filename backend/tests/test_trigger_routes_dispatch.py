import pytest
from app import create_app


@pytest.fixture
def client(isolated_db):
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestTriggerRouteDispatchFields:
    def test_create_trigger_with_dispatch_type(self, client):
        resp = client.post(
            "/admin/triggers/",
            json={
                "name": "sa-trigger",
                "prompt_template": "do {message}",
                "dispatch_type": "super_agent",
                "super_agent_id": "sa-abc123",
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        trigger_id = data["trigger_id"]

        resp = client.get(f"/admin/triggers/{trigger_id}")
        assert resp.status_code == 200
        detail = resp.get_json()
        assert detail["dispatch_type"] == "super_agent"
        assert detail["super_agent_id"] == "sa-abc123"

    def test_update_trigger_dispatch_type(self, client):
        resp = client.post(
            "/admin/triggers/",
            json={"name": "update-test", "prompt_template": "test"},
        )
        trigger_id = resp.get_json()["trigger_id"]

        resp = client.put(
            f"/admin/triggers/{trigger_id}",
            json={
                "dispatch_type": "super_agent",
                "super_agent_id": "sa-xyz789",
            },
        )
        assert resp.status_code == 200

        resp = client.get(f"/admin/triggers/{trigger_id}")
        detail = resp.get_json()
        assert detail["dispatch_type"] == "super_agent"
        assert detail["super_agent_id"] == "sa-xyz789"
