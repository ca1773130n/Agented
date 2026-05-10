"""v0.7.8: admin endpoints for the cached + auth-aware model discovery.

Three endpoints power the operator console:
- ``GET  /admin/backends/{backend_kind}/models`` — returns cached models
  for the given (backend_kind, auth_method) pair, populating from
  discovery on a miss/expiry.
- ``POST /admin/backends/{backend_kind}/models/refresh`` — forces a
  re-discovery and stores the result.
- ``GET  /admin/backends/models/cache`` — operator-overview list of all
  cache entries (backend × auth_method).

All require admin via ``requires_role("admin")``.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, get, post

from app.services import model_cache_service
from app_litestar.auth_guards import requires_role


@get(
    "/{backend_kind:str}/models",
    sync_to_thread=True,
    guards=[requires_role("admin")],
)
def get_models(backend_kind: str, auth_method: str = "unknown") -> dict[str, Any]:
    models, meta = model_cache_service.get_models(
        backend_kind=backend_kind, auth_method=auth_method
    )
    return {"models": models, **meta}


@post(
    "/{backend_kind:str}/models/refresh",
    sync_to_thread=True,
    guards=[requires_role("admin")],
)
def refresh_models(backend_kind: str, auth_method: str = "unknown") -> dict[str, Any]:
    return model_cache_service.refresh(backend_kind, auth_method)


@get(
    "/models/cache",
    sync_to_thread=True,
    guards=[requires_role("admin")],
)
def list_cache() -> dict[str, Any]:
    return {"entries": model_cache_service.list_all()}


model_cache_router = Router(
    path="/admin/backends",
    route_handlers=[get_models, refresh_models, list_cache],
)
