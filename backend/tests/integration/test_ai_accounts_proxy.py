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
    assert body["version"] == "0.2.0"


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
