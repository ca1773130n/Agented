"""RBAC management API endpoints — fully retired in waves 23-30.

The entire /admin/rbac namespace now lives on the Litestar app at :20002:
- GET    /admin/rbac/permissions          (wave 23)
- GET    /admin/rbac/roles                (wave 26)
- GET    /admin/rbac/roles/{role_id}      (wave 27)
- POST   /admin/rbac/roles                (wave 28)
- PUT    /admin/rbac/roles/{role_id}      (wave 29)
- DELETE /admin/rbac/roles/{role_id}      (wave 30)
- POST   /admin/rbac/roles/{role_id}/rotate (wave 24)

The vite dev proxy routes /admin/rbac/* to :20002 so the frontend remains
unchanged. This blueprint stays as a stub purely so the Flask app
factory's import doesn't break — we'll drop the import once a future
migration wave touches the create_app surface.
"""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="rbac", description="Role-Based Access Control management (Litestar)")
rbac_bp = APIBlueprint("rbac", __name__, url_prefix="/admin/rbac", abp_tags=[tag])
