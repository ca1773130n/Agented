"""Policy / governance routes (phase 23, 23-04).

The backend surface for the stackable policy engine (``PolicyService``):

  - ``/admin/policies``            GET   — list policies (optional ``scope`` filter)
  - ``/admin/policies``            PUT   — upsert (create when no ``id``, else update)
  - ``/admin/policies/{id}``       DELETE— remove a policy
  - ``/admin/policies/decision``   POST  — resolve a pending ASK for a session

The CRUD handlers mirror ``budgets_router`` (budgets.py:292). The ``/decision``
handler mirrors ``grd_routes.loop_gate_decision`` (grd_routes.py:1441): it is the
HTTP entry point the frontend ASK card POSTs to, forwarding to
``PolicyService.submit_policy_decision`` (the in-process session-keyed registry
the ``await_decision`` poll loop watches).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import ClientException, NotFoundException
from litestar.params import Parameter

from app.services.policy_service import PolicyService

from ..auth_guards import requires_role

logger = logging.getLogger(__name__)

# Authoring surface validation (mirrors budgets.set_limit's hardcoded enum
# checks). Builtin kinds are the ``_BUILTINS`` dispatch keys in policy_service;
# "custom" rows fall back to their stored ``effect`` verbatim.
_VALID_SCOPES = ("server", "team", "session")
_BUILTIN_KINDS = (
    "cost_budget",
    "max_tool_calls_per_session",
    "ask_on_os_tools",
    "enforce_sandbox",
)
_VALID_KINDS = _BUILTIN_KINDS + ("custom",)
_VALID_EFFECTS = ("allow", "deny", "ask")
_VALID_DECISIONS = ("approve", "deny")


@get("", sync_to_thread=False)
def list_policies(
    # ``scope`` is a Litestar-reserved kwarg (it injects the ASGI scope), so the
    # query param is bound to ``scope_filter`` via an alias.
    scope_filter: Optional[str] = Parameter(query="scope", default=None, required=False),
) -> dict[str, Any]:
    """List policies, optionally filtered by ``scope`` (server|team|session)."""
    if scope_filter is not None and scope_filter not in _VALID_SCOPES:
        raise ClientException(detail=f"scope must be one of {_VALID_SCOPES}")
    return {"policies": PolicyService.list_policies(scope=scope_filter)}


@put("", sync_to_thread=False)
def upsert_policy(data: dict) -> dict[str, Any]:
    """Create a policy (no ``id``) or update an existing one (``id`` present).

    Validates scope ∈ {server,team,session}, kind ∈ builtin set + "custom",
    effect ∈ {allow,deny,ask}. Raises 400 on bad input, 404 on update-miss.
    """
    if not data:
        raise ClientException(detail="JSON body required")

    policy_id = data.get("id")
    scope = data.get("scope")
    kind = data.get("kind")
    effect = data.get("effect", "ask")

    if scope is not None and scope not in _VALID_SCOPES:
        raise ClientException(detail=f"scope must be one of {_VALID_SCOPES}")
    if kind is not None and kind not in _VALID_KINDS:
        raise ClientException(detail=f"kind must be one of {_VALID_KINDS}")
    if effect is not None and effect not in _VALID_EFFECTS:
        raise ClientException(detail=f"effect must be one of {_VALID_EFFECTS}")

    fields: dict[str, Any] = {}
    for key in ("scope", "scope_id", "kind", "effect", "params", "enabled", "priority"):
        if key in data:
            fields[key] = data[key]

    if policy_id:
        updated = PolicyService.update_policy(policy_id, **fields)
        if updated is None:
            raise NotFoundException(detail=f"No policy found with id {policy_id}")
        return updated

    # Create path — scope + kind are required.
    if not scope:
        raise ClientException(detail="scope is required")
    if not kind:
        raise ClientException(detail="kind is required")
    return PolicyService.create_policy(
        scope=scope,
        scope_id=data.get("scope_id"),
        kind=kind,
        effect=effect or "ask",
        params=data.get("params"),
        enabled=data.get("enabled", 1),
        priority=data.get("priority", 0),
    )


@delete("/{policy_id:str}", sync_to_thread=False)
def remove_policy(policy_id: str) -> None:
    """Delete a policy. 404 when the id does not exist."""
    if not PolicyService.delete_policy(policy_id):
        raise NotFoundException(detail=f"No policy found with id {policy_id}")


@post("/decision", sync_to_thread=False)
def decide(data: dict) -> dict[str, Any]:
    """Resolve a pending ASK for a session.

    Body: ``{session_id, decision in {approve,deny}, message?}``. Mirrors
    ``grd_routes.loop_gate_decision``: forwards to
    ``PolicyService.submit_policy_decision`` and returns whether a wait was
    pending (``ok``).
    """
    body = data or {}
    session_id = body.get("session_id")
    decision = body.get("decision")
    if not session_id:
        raise ClientException(detail="session_id is required")
    if decision not in _VALID_DECISIONS:
        raise ClientException(detail=f"decision must be one of {_VALID_DECISIONS}")
    pending = PolicyService.submit_policy_decision(session_id, decision, body.get("message"))
    return {"ok": pending}


policies_router = Router(
    path="/admin/policies",
    # SECURITY (23 BLOCKER 2): policies ARE the governance substrate — an
    # attacker who can mutate them can disable every other control. Gate the
    # WHOLE router at admin (mirrors secrets_router) so listing, upsert, delete
    # AND /decision (resolving a pending ASK) all require a real admin principal.
    # Without this, the coarse /admin/ defaults let an *editor* PUT/POST and a
    # *viewer* GET. A coarse-table safety net for /admin/policies is also added
    # in auth_guards.ROLE_REQUIRED (defence in depth).
    guards=[requires_role("admin")],
    route_handlers=[list_policies, upsert_policy, remove_policy, decide],
)
