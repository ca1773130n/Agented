"""Model pricing API endpoint."""

from flask_openapi3 import APIBlueprint, Tag

from app.services.session_cost_service import _PRICING

tag = Tag(name="ModelPricing", description="Model pricing information")
model_pricing_bp = APIBlueprint("model_pricing", __name__, url_prefix="/api", abp_tags=[tag])

# Static metadata not present in _PRICING
_MODEL_META = {
    "claude-opus-4-6": {"name": "Claude Opus 4.6", "contextWindow": 200000, "speed": "slow"},
    "claude-opus-4-5": {"name": "Claude Opus 4.5", "contextWindow": 200000, "speed": "slow"},
    "claude-opus-4": {"name": "Claude Opus 4", "contextWindow": 200000, "speed": "slow"},
    "claude-sonnet-4-5": {"name": "Claude Sonnet 4.5", "contextWindow": 200000, "speed": "medium"},
    "claude-sonnet-4": {"name": "Claude Sonnet 4", "contextWindow": 200000, "speed": "medium"},
    "claude-haiku-4-5": {"name": "Claude Haiku 4.5", "contextWindow": 200000, "speed": "fast"},
    "claude-haiku-3-5": {"name": "Claude Haiku 3.5", "contextWindow": 200000, "speed": "fast"},
    "gpt-5.3-codex": {"name": "GPT-5.3 Codex", "contextWindow": 128000, "speed": "medium"},
    "gpt-5-codex-mini": {"name": "GPT-5 Codex Mini", "contextWindow": 128000, "speed": "fast"},
    "codex-mini-latest": {"name": "Codex Mini Latest", "contextWindow": 128000, "speed": "fast"},
}


@model_pricing_bp.get("/models/pricing")
def get_model_pricing():
    """Return pricing information for all known models."""
    models = []
    for model_id, pricing in _PRICING.items():
        meta = _MODEL_META.get(model_id, {})
        models.append(
            {
                "id": model_id,
                "name": meta.get("name", model_id),
                "inputPricePer1M": pricing.get("input", 0.0),
                "outputPricePer1M": pricing.get("output", 0.0),
                "contextWindow": meta.get("contextWindow", 200000),
                "speed": meta.get("speed", "medium"),
            }
        )
    return {"models": models}
