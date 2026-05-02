"""Migrated to Litestar :20002 across waves 45 + 73.

Wave 45: /api/version + /api/check-backend + /api/validate-path.
Wave 73: /api/{validate-github-url, resolve-issues, discover-skills, browse-directory, create-directory}.
"""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="utility", description="Migrated to Litestar")
utility_bp = APIBlueprint("utility", __name__, url_prefix="/api", abp_tags=[tag])
