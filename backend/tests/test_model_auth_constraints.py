"""v0.7.8: model_auth_constraints.filter_models behaviour."""

from app.services.model_auth_constraints import filter_models


def test_api_key_auth_keeps_everything():
    models = ["gpt-5.1", "gpt-5.1-codex-mini", "gpt-4o", "o1"]
    assert filter_models("codex", "api_key", models) == models


def test_chatgpt_auth_codex_filters_out_api_only_models():
    models = ["gpt-5.1", "gpt-5.1-codex-mini", "gpt-5", "o1"]
    out = filter_models("codex", "chatgpt", models)
    assert "gpt-5.1" not in out
    assert "gpt-5.1-codex-mini" not in out
    assert "gpt-5" in out
    assert "o1" in out


def test_unknown_backend_kind_passes_through_unchanged():
    models = ["whatever-model", "another-model"]
    assert filter_models("imaginary-backend", "oauth", models) == models


def test_empty_model_list_returns_empty():
    assert filter_models("codex", "chatgpt", []) == []
    assert filter_models("codex", "api_key", []) == []


def test_returns_a_new_list_not_the_input():
    """Defensive: callers shouldn't see mutations through aliasing."""
    models = ["gpt-5"]
    out = filter_models("codex", "api_key", models)
    out.append("mutation")
    assert models == ["gpt-5"]
