"""Permission-prompt registry tests (v0.7.69).

The hook script POSTs to ``/permission-request`` and the endpoint
blocks on ``registry.wait_for_decision(rid)``. A separate request
hits ``/permission-decision`` and ``registry.resolve(rid, ...)``
unblocks the wait. These tests pin the wait/notify contract.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.services.permission_prompt_service import PermissionPromptRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    PermissionPromptRegistry._pending.clear()
    yield
    PermissionPromptRegistry._pending.clear()


def test_register_returns_distinct_request_ids():
    a = PermissionPromptRegistry.register("psess-1", "Bash", {"command": "ls"})
    b = PermissionPromptRegistry.register("psess-1", "Bash", {"command": "ls"})
    assert a.request_id != b.request_id
    assert a.request_id.startswith("perm-")


def test_resolve_unblocks_wait():
    """Classic producer/consumer — the wait MUST return the decision
    after another thread resolves the request."""
    req = PermissionPromptRegistry.register(
        "psess-1", "Bash", {"command": "ls"}
    )
    decisions: list[str | None] = []

    def waiter() -> None:
        decisions.append(
            PermissionPromptRegistry.wait_for_decision(req.request_id, timeout=2.0)
        )

    t = threading.Thread(target=waiter)
    t.start()
    # Brief sleep so the waiter is actually parked on event.wait
    time.sleep(0.05)
    assert PermissionPromptRegistry.resolve(req.request_id, "allow") is True
    t.join(timeout=2.0)

    assert decisions == ["allow"]
    # Registry cleaned up
    assert req.request_id not in PermissionPromptRegistry._pending


def test_wait_times_out_returns_none():
    req = PermissionPromptRegistry.register(
        "psess-1", "Bash", {"command": "ls"}
    )
    decision = PermissionPromptRegistry.wait_for_decision(
        req.request_id, timeout=0.05
    )
    assert decision is None
    # Registry cleaned up on timeout too
    assert req.request_id not in PermissionPromptRegistry._pending


def test_resolve_rejects_invalid_decision():
    req = PermissionPromptRegistry.register("psess-1", "Bash", {})
    assert PermissionPromptRegistry.resolve(req.request_id, "maybe") is False
    assert PermissionPromptRegistry.resolve(req.request_id, "") is False


def test_resolve_unknown_request_id():
    assert PermissionPromptRegistry.resolve("perm-nope", "allow") is False


def test_cancel_session_unblocks_waiters():
    """Tearing down a session drops every pending request for it.
    Each parked hook gets ``None`` and the registry is purged."""
    r1 = PermissionPromptRegistry.register("psess-1", "Bash", {})
    r2 = PermissionPromptRegistry.register("psess-1", "Read", {})
    r3 = PermissionPromptRegistry.register("psess-2", "Bash", {})

    decisions: list[str | None] = []

    def waiter(rid: str) -> None:
        decisions.append(
            PermissionPromptRegistry.wait_for_decision(rid, timeout=2.0)
        )

    ts = [
        threading.Thread(target=waiter, args=(r1.request_id,)),
        threading.Thread(target=waiter, args=(r2.request_id,)),
        threading.Thread(target=waiter, args=(r3.request_id,)),
    ]
    for t in ts:
        t.start()
    time.sleep(0.05)
    assert PermissionPromptRegistry.cancel_session("psess-1") == 2
    for t in ts[:2]:
        t.join(timeout=2.0)

    # The two waiters for psess-1 got None (cancelled). r3 (psess-2)
    # is still parked — kill it so the test doesn't hang on join.
    none_count = sum(1 for d in decisions if d is None)
    assert none_count == 2
    PermissionPromptRegistry.resolve(r3.request_id, "deny")
    ts[2].join(timeout=2.0)


def test_double_resolve_no_op():
    """Once a request is resolved, a second resolve call is a no-op
    (returns False). Mostly defensive — the registry purges on
    successful resolve so this exercises the dict.get() guard."""
    req = PermissionPromptRegistry.register("psess-1", "Bash", {})
    assert PermissionPromptRegistry.resolve(req.request_id, "allow") is True
    # Forget the wait so the entry stays in pending
    PermissionPromptRegistry._pending[req.request_id] = req
    # event.is_set() is already True from the first resolve
    assert PermissionPromptRegistry.resolve(req.request_id, "deny") is False
