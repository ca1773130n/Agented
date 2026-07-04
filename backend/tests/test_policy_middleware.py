"""PolicyMiddleware tests (23-04, SC4).

Proves the governance-scope annotation middleware:
  1. For a request whose path carries a session id, it annotates the request
     (``policy_scope_var`` contextvar + ``scope["state"]["policy"]``) and echoes
     an ``X-Policy-Scope`` response header.
  2. For an unrelated route it is a clean pass-through — no header, no contextvar,
     status + body unchanged.
  3. It never blocks / never alters an unrelated response.

Isolation note (Phase 25 follow-up C): ``test_litestar_middleware.py`` calls
``importlib.reload(app_litestar.middleware)`` to make ``SecurityHeadersMiddleware``
re-read ``FORCE_HTTPS``. That reload rebinds ``policy_scope_var`` (and every
middleware class) to BRAND-NEW objects in the module dict. If this file captured
``PolicyMiddleware``/``policy_scope_var`` at import time, then — depending on
collection order — the route handler here could read one ContextVar object while
``PolicyMiddleware.handle`` (whose global lookup follows the live, reloaded module
dict) sets a DIFFERENT one, so ``policy_scope_var.get()`` inside the handler
returned ``None`` and the annotation assertion failed. To stay order-independent we
resolve BOTH the middleware class and the contextvar from the live module inside
each test/handler — the SAME lookup path ``PolicyMiddleware.handle`` uses — so all
three (handler read, middleware set, assertion) always agree on one object.
"""

from __future__ import annotations

from typing import Any

from litestar import get
from litestar.testing import create_test_client

import app_litestar.middleware as mw


def _policy_scope_var():
    """The live contextvar from the (possibly reloaded) middleware module."""
    return mw.policy_scope_var


@get("/projects/{project_id:str}/sessions/{session_id:str}/info", sync_to_thread=False)
def _session_route(project_id: str, session_id: str) -> dict[str, Any]:
    # Reads the contextvar the middleware set for this request — resolved LIVE
    # from the module so a prior ``importlib.reload`` can't split us onto a stale
    # ContextVar object that PolicyMiddleware.handle no longer writes.
    return {"ok": True, "policy": mw.policy_scope_var.get()}


@get("/plain", sync_to_thread=False)
def _plain_route() -> dict[str, Any]:
    return {"ok": True, "policy": mw.policy_scope_var.get()}


def _client():
    return create_test_client(
        route_handlers=[_session_route, _plain_route],
        middleware=[mw.PolicyMiddleware()],
    )


def test_annotates_request_carrying_session_id():
    with _client() as c:
        r = c.get("/projects/proj-1/sessions/sess-abc/info")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # contextvar annotation present + correct.
    assert body["policy"] == {"session_id": "sess-abc", "scope": "session"}
    # response header echoes the scope.
    assert r.headers.get("x-policy-scope") == "session:sess-abc"


def test_pass_through_for_unrelated_route():
    with _client() as c:
        r = c.get("/plain")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "policy": None}
    # No annotation header on a non-session route.
    assert "x-policy-scope" not in {k.lower() for k in r.headers}


def test_contextvar_does_not_leak_between_requests():
    """The contextvar is reset after each request (no cross-request bleed)."""
    with _client() as c:
        c.get("/projects/p/sessions/s1/info")
        r = c.get("/plain")
    # The plain route must observe None even after a prior session request.
    assert r.json()["policy"] is None
    # And the module-level contextvar default is restored outside any request.
    assert _policy_scope_var().get() is None


def test_unrelated_response_body_is_byte_identical():
    """The middleware must not mutate the body of an unrelated response — compare
    bytes against the same handler mounted WITHOUT PolicyMiddleware."""
    with _client() as c:
        with_mw = c.get("/plain")
    with create_test_client(route_handlers=[_plain_route]) as c2:
        without_mw = c2.get("/plain")
    assert with_mw.content == without_mw.content
    assert with_mw.status_code == without_mw.status_code == 200
