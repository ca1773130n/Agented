"""Migrated to Litestar :20002 (waves 73 + 78)."""

from flask_openapi3 import APIBlueprint

backends_bp = APIBlueprint("backends", __name__, url_prefix="/admin/backends")
