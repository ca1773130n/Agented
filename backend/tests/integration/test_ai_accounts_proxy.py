"""Integration smoke test for the mounted ai-accounts Litestar app.

Boots the ASGI app in-process via Litestar's AsyncTestClient — no uvicorn,
no real port. Proves that the dep is wired and the basic route surface answers.
The AsyncTestClient handles the on_startup lifespan (DB migration) correctly.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from litestar.testing import AsyncTestClient

from ai_accounts_core.adapters.auth_noauth import NoAuth
from ai_accounts_core.adapters.storage_sqlite import SqliteStorage
from ai_accounts_core.backends import ClaudeBackend, OpenCodeBackend
from ai_accounts_core.testing import FakeBackend, FakeVault
from ai_accounts_litestar.app import create_app
from ai_accounts_litestar.config import AiAccountsConfig


@pytest_asyncio.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncTestClient]:
    app = create_app(
        AiAccountsConfig(
            env="development",
            storage=SqliteStorage(str(tmp_path / "t.db")),
            vault=FakeVault(),
            auth=NoAuth(),
            backends=(ClaudeBackend(), OpenCodeBackend()),
            backend_dirs_path=tmp_path / "backend_dirs",
        )
    )
    async with AsyncTestClient(app=app) as c:
        yield c


@pytest_asyncio.fixture
async def fake_client(tmp_path: Path) -> AsyncIterator[AsyncTestClient]:
    """Fixture with FakeBackend for onboarding smoke tests — deterministic detect."""
    app = create_app(
        AiAccountsConfig(
            env="development",
            storage=SqliteStorage(str(tmp_path / "fake.db")),
            vault=FakeVault(),
            auth=NoAuth(),
            backends=(FakeBackend(),),
            backend_dirs_path=tmp_path / "backend_dirs",
        )
    )
    async with AsyncTestClient(app=app) as c:
        yield c


@pytest.mark.asyncio
async def test_health(client: AsyncTestClient):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"].startswith("0.2.")


@pytest.mark.asyncio
async def test_list_backends_empty(client: AsyncTestClient):
    response = await client.get("/api/v1/backends/")
    assert response.status_code == 200
    assert response.json() == {"items": []}


@pytest.mark.asyncio
async def test_create_then_list(client: AsyncTestClient):
    response = await client.post(
        "/api/v1/backends/",
        json={"kind": "claude", "display_name": "Integration Test"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "claude"
    assert body["display_name"] == "Integration Test"
    assert body["id"].startswith("bkd-")

    listed = await client.get("/api/v1/backends/")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == body["id"]


@pytest.mark.asyncio
async def test_unknown_kind_returns_400(client: AsyncTestClient):
    response = await client.post(
        "/api/v1/backends/",
        json={"kind": "martian", "display_name": "X"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "backend_kind_unknown"


@pytest.mark.asyncio
async def test_missing_backend_returns_404(client: AsyncTestClient):
    response = await client.get("/api/v1/backends/bkd-nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "backend_not_found"


@pytest.mark.asyncio
async def test_onboarding_full_flow(fake_client: AsyncTestClient):
    """Smoke test: start → detect → pick → login → finalize via FakeBackend."""
    # Start a new onboarding session
    started = await fake_client.post("/api/v1/onboarding/")
    assert started.status_code == 201
    body = started.json()
    onb_id = body["id"]
    assert onb_id.startswith("onb-")
    assert body["current_step"] == "welcome"

    # Run detection — FakeBackend.detect() always returns installed=True
    detect = await fake_client.post(f"/api/v1/onboarding/{onb_id}/detect")
    assert detect.status_code == 201
    results = detect.json()["results"]
    assert "fake" in results
    assert results["fake"]["installed"] is True

    # Pick the fake backend
    pick = await fake_client.post(
        f"/api/v1/onboarding/{onb_id}/pick",
        json={"kind": "fake", "display_name": "Integration Test"},
    )
    assert pick.status_code == 201
    assert pick.json()["kind"] == "fake"

    # Login with api_key flow — FakeBackend returns a CredentialLogin immediately
    login = await fake_client.post(
        f"/api/v1/onboarding/{onb_id}/login",
        json={"flow_kind": "api_key", "inputs": {}},
    )
    assert login.status_code == 201
    assert login.json()["kind"] == "complete"

    # Finalize the onboarding session
    final = await fake_client.post(f"/api/v1/onboarding/{onb_id}/finalize")
    assert final.status_code == 201
    assert final.json()["current_step"] == "done"
