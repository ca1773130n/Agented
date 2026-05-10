"""Per-backend auth-method constraints — which models a given login type
cannot serve. Maintained as a hand-curated list because the upstream
('not supported when using X with a Y account') errors are not consistently
machine-readable."""

from __future__ import annotations

# Models that REQUIRE an API key — auth methods other than 'api_key' must
# filter these out. Empty set ⇒ no constraints for that backend.
_API_KEY_ONLY_MODELS: dict[str, frozenset[str]] = {
    "codex": frozenset({"gpt-5.1", "gpt-5.1-codex-mini"}),
}


def filter_models(backend_kind: str, auth_method: str, models: list[str]) -> list[str]:
    """Drop models the given auth_method cannot serve."""
    if auth_method == "api_key":
        return list(models)
    blocked = _API_KEY_ONLY_MODELS.get(backend_kind, frozenset())
    if not blocked:
        return list(models)
    return [m for m in models if m not in blocked]
