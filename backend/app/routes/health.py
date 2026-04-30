"""Health check endpoints — fully retired in wave 37.

The entire /health/* namespace now lives on the Litestar app at :20002
(see backend/app_litestar/routes/health.py). The vite dev proxy routes
/health/* to :20002 so the frontend remains unchanged.

This stub keeps the blueprint export so the Flask app factory's import
doesn't break — to be dropped once a future migration touches the
create_app surface.
"""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="health", description="Health check endpoints (Litestar)")
health_bp = APIBlueprint("health", __name__, url_prefix="/health", abp_tags=[tag])
