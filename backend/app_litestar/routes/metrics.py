"""v0.6.2: /admin/metrics endpoint — Prometheus text format."""

from __future__ import annotations

from litestar import Router, get
from litestar.response import Response

from app_litestar.auth_guards import requires_role
from app_litestar.metrics import registry


@get(
    "/metrics",
    sync_to_thread=False,
    guards=[requires_role("admin")],
)
def metrics_endpoint() -> Response:
    """Prometheus exposition format. Admin-only.

    Scrape config (Prometheus YAML):
      - job_name: agented
        metrics_path: /admin/metrics
        bearer_token: <admin session token>
        static_configs:
          - targets: ['agented.local:20000']
    """
    body = registry.render_text()
    return Response(
        content=body,
        media_type="text/plain; version=0.0.4",
        status_code=200,
    )


metrics_router = Router(path="/admin", route_handlers=[metrics_endpoint])
