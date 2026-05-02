"""Migrated to Litestar :20002 in wave 69 — see app_litestar/routes/leaf_crud_e.py."""

from flask_openapi3 import APIBlueprint

orchestration_bp = APIBlueprint(
    "orchestration", __name__, url_prefix="/admin/orchestration"
)
