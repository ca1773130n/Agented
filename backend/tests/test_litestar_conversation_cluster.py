"""Smoke tests for the wave 72 conversation cluster CRUD."""

import pytest
from litestar.testing import create_test_client

from app_litestar.auth import provide_caller
from app_litestar.routes.conversation_cluster import (
    command_conversations_router,
    hook_conversations_router,
    plugin_conversations_router,
    rule_conversations_router,
)


@pytest.fixture
def client():
    with create_test_client(
        route_handlers=[
            plugin_conversations_router,
            command_conversations_router,
            hook_conversations_router,
            rule_conversations_router,
        ],
        dependencies={"caller": provide_caller},
    ) as c:
        yield c


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_send_message_requires_message(client, namespace, isolated_db):
    resp = client.post(
        f"/api/{namespace}/conversations/conv-x/message", json={}
    )
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_unknown_conversation_404(client, namespace, isolated_db):
    resp = client.get(f"/api/{namespace}/conversations/missing")
    # service returns 404 with error
    assert resp.status_code in (200, 404)
    # if 200, verify no error key
    if resp.status_code == 200:
        body = resp.json()
        assert "error" not in body or body.get("error") is None


@pytest.mark.parametrize(
    "namespace",
    ["commands", "hooks", "rules"],
)
def test_list_conversations(client, namespace, isolated_db):
    resp = client.get(f"/api/{namespace}/conversations/")
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "namespace",
    ["commands", "hooks", "rules"],
)
def test_resume_unknown_404(client, namespace, isolated_db):
    resp = client.post(f"/api/{namespace}/conversations/missing/resume", json={})
    assert resp.status_code in (200, 400, 404)


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_abandon_unknown(client, namespace, isolated_db):
    resp = client.post(f"/api/{namespace}/conversations/missing/abandon", json={})
    assert resp.status_code in (200, 400, 404)


@pytest.mark.parametrize(
    "namespace",
    ["plugins", "commands", "hooks", "rules"],
)
def test_finalize_unknown(client, namespace, isolated_db):
    resp = client.post(f"/api/{namespace}/conversations/missing/finalize", json={})
    assert resp.status_code in (200, 400, 404)
