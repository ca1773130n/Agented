"""Session cost computation — pricing data and cost calculation."""

# Pricing per million tokens (USD) — mirrors BudgetService.MODEL_PRICING
_PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_create": 18.75},
    "claude-opus-4-5": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_create": 18.75},
    "claude-opus-4": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_create": 18.75},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_create": 3.75},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_create": 3.75},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_create": 1.0},
    "claude-haiku-3-5": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_create": 1.0},
    # Codex / OpenAI models (approximate per-million-token pricing)
    "gpt-5.3-codex": {"input": 2.0, "output": 8.0, "cache_read": 0.5, "cache_create": 0.0},
    "gpt-5-codex-mini": {"input": 0.30, "output": 1.20, "cache_read": 0.075, "cache_create": 0.0},
    "codex-mini-latest": {"input": 0.30, "output": 1.20, "cache_read": 0.075, "cache_create": 0.0},
}


def _resolve_model_pricing(model_id: str) -> dict:
    """Find best pricing match for a model ID string."""
    if not model_id:
        return _PRICING.get("claude-sonnet-4", {})

    mid = model_id.lower()
    # Try direct match
    if mid in _PRICING:
        return _PRICING[mid]

    # Fuzzy match by prefix
    for key in _PRICING:
        if mid.startswith(key) or key in mid:
            return _PRICING[key]

    # Family-level fallback
    if "opus" in mid:
        return _PRICING["claude-opus-4"]
    if "sonnet" in mid:
        return _PRICING["claude-sonnet-4"]
    if "haiku" in mid:
        return _PRICING["claude-haiku-4-5"]
    if "codex" in mid or "gpt-5" in mid:
        return _PRICING.get("gpt-5.3-codex", {})

    return _PRICING.get("claude-sonnet-4", {})


def _compute_cost(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_creation_tokens: int,
    model: str,
) -> float:
    """Compute USD cost from token counts and model pricing."""
    p = _resolve_model_pricing(model)
    if not p:
        return 0.0
    cost = (
        input_tokens * p.get("input", 0)
        + output_tokens * p.get("output", 0)
        + cache_read_tokens * p.get("cache_read", 0)
        + cache_creation_tokens * p.get("cache_create", 0)
    ) / 1_000_000
    return round(cost, 6)
