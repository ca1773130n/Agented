"""Migrated to Litestar :20002 in wave 48 — see app_litestar/routes/misc.py."""

from flask_openapi3 import APIBlueprint, Tag

tag = Tag(name="ModelPricing", description="Migrated to Litestar")
model_pricing_bp = APIBlueprint("model_pricing", __name__, url_prefix="/api", abp_tags=[tag])
