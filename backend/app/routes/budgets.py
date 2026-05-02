"""Migrated to Litestar :20002 in wave 59 — see app_litestar/routes/budgets.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="budgets", description="Migrated to Litestar")
budgets_bp = APIBlueprint("budgets", __name__, url_prefix="/admin/budgets", abp_tags=[tag])
