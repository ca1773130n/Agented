"""Tests for ModelDiscoveryService.cheap_model_for — live-catalog cheap-model
resolution. This is the guard against hardcoded model ids going stale and 502-ing
"unknown provider for model" (the o4-mini / gemini-2.5-flash class of bug)."""

from __future__ import annotations

import app.services.model_discovery_service as mds
from app.services.model_discovery_service import ModelDiscoveryService


def _patch_catalog(monkeypatch, by_owner: dict):
    monkeypatch.setattr(
        ModelDiscoveryService,
        "_discover_models_via_cliproxy",
        classmethod(lambda cls, owned_by: by_owner.get(owned_by)),
    )
    mds._cheap_model_cache.clear()


def test_picks_haiku_over_opus_and_sonnet(monkeypatch):
    _patch_catalog(
        monkeypatch,
        {"anthropic": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]},
    )
    assert ModelDiscoveryService.cheap_model_for("claude") == "claude-haiku-4-5-20251001"


def test_picks_mini_for_codex_excluding_image_and_review(monkeypatch):
    _patch_catalog(
        monkeypatch,
        {"openai": ["gpt-image-2", "gpt-5.5", "gpt-5.4-mini", "gpt-5.4", "codex-auto-review"]},
    )
    assert ModelDiscoveryService.cheap_model_for("codex") == "gpt-5.4-mini"


def test_excludes_pro_and_picks_flash_lite_for_gemini(monkeypatch):
    _patch_catalog(
        monkeypatch,
        {
            "google": [
                "gemini-3.1-pro-preview",
                "gemini-3.1-flash-lite-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash-lite",
            ]
        },
    )
    picked = ModelDiscoveryService.cheap_model_for("gemini")
    assert picked == "gemini-3.1-flash-lite-preview"
    assert "pro" not in picked


def test_none_when_catalog_empty(monkeypatch):
    _patch_catalog(monkeypatch, {"anthropic": []})
    assert ModelDiscoveryService.cheap_model_for("claude") is None


def test_none_for_unknown_backend(monkeypatch):
    _patch_catalog(monkeypatch, {})
    assert ModelDiscoveryService.cheap_model_for("opencode") is None


def test_result_is_cached(monkeypatch):
    calls = {"n": 0}

    def _disc(cls, owned_by):
        calls["n"] += 1
        return ["claude-haiku-4-5-20251001"]

    monkeypatch.setattr(ModelDiscoveryService, "_discover_models_via_cliproxy", classmethod(_disc))
    mds._cheap_model_cache.clear()
    a = ModelDiscoveryService.cheap_model_for("claude")
    b = ModelDiscoveryService.cheap_model_for("claude")
    assert a == b == "claude-haiku-4-5-20251001"
    assert calls["n"] == 1  # cached after the first resolution


def test_none_is_not_cached_so_it_retries(monkeypatch):
    """Proxy down at first call → None, NOT cached → resolves once it comes up."""
    state = {"up": False}

    def _disc(cls, owned_by):
        return ["gpt-5.4-mini"] if state["up"] else None

    monkeypatch.setattr(ModelDiscoveryService, "_discover_models_via_cliproxy", classmethod(_disc))
    mds._cheap_model_cache.clear()
    assert ModelDiscoveryService.cheap_model_for("codex") is None
    state["up"] = True
    assert ModelDiscoveryService.cheap_model_for("codex") == "gpt-5.4-mini"
