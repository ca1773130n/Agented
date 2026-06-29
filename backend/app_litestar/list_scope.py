"""Admin-aware list scoping for ``/admin/*`` collection endpoints.

The single-operator admin (API-key auth) often has a blank/legacy ``user_id`` that
matches none of the owned rows — filtering it would hide everything (this is the
bug that hid products/projects/sketches/etc. from the operator). So, uniformly:

  * an **admin** caller sees **ALL** rows (oversight) — never hidden by a
    blank/legacy/mismatched user_id;
  * a **non-admin** caller is scoped to their **own** rows;
  * a non-admin with **no resolvable** user_id sees **NOTHING** (never the
    unscoped list — closes a latent leak for malformed api-key rows).

Only the "all" branch differs per collection, so callers pass an ``all_`` thunk;
the scoped + empty + admin-routing logic lives here.
"""

from typing import Any, Callable, Optional

from app.db.owned_entities import get_for_user
from app.logging_config import current_user_var

from .auth import Caller


def admin_or_scoped(
    caller: Caller,
    table: str,
    plural: str,
    *,
    all_: Callable[[], dict[str, Any]],
    scoped: Optional[Callable[[str], dict[str, Any]]] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Resolve a collection listing by role.

    ``table`` is the ``owned_entities`` table for the per-user scope; ``plural`` is
    the response key (e.g. ``"servers"``); ``all_`` returns the full unscoped
    response dict for admins. ``scoped`` overrides the default per-user query for
    collections whose scoped path carries extra params (search/sort + a real
    ``count_for_user`` total) — it receives the resolved user_id and returns the
    full response dict.
    """
    if caller.role == "admin":
        return all_()
    user_id = caller.user_id or current_user_var.get()
    if not user_id:
        return {plural: [], "total_count": 0}
    if scoped is not None:
        return scoped(user_id)
    rows = get_for_user(table, user_id, limit=limit, offset=offset)
    return {plural: rows, "total_count": len(rows)}
