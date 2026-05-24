"""PR-J3b: integration stubs for STUB-DEFER frontend views (PR-J3).

The GitHub App install flow (GitHubAppInstallPage.vue) calls
`/admin/integrations/github/installations` and `/admin/integrations/github/install`.
Neither has a real handler yet; the frontend ships a "Not yet enabled" banner
in PR-J3. These 501 handlers replace the previous 404s so the UI sees an
explicit contract.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, get, post
from litestar.exceptions import HTTPException


@get("/installations", sync_to_thread=False)
def list_github_installations() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/install", sync_to_thread=False)
def install_github_app(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


integrations_github_router = Router(
    path="/admin/integrations/github",
    route_handlers=[list_github_installations, install_github_app],
)
