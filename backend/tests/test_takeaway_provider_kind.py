"""Provider-kind threading through LLM takeaway extraction."""

from __future__ import annotations

from unittest.mock import patch

from app.services import harness_takeaway_extractor as tx
from app.services.harness_failure_annotator import SessionPayload


def _payload(text: str) -> SessionPayload:
    return SessionPayload(
        text=text, backend_type="claude", project_id="proj-1", outcome="completed"
    )


def test_extract_llm_uses_provider_cmd(monkeypatch):
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    captured = {}

    def _fake_run(prompt, *, cmd_template, timeout):
        captured["cmd_template"] = cmd_template
        return "[]"

    big_text = "x" * 5000  # exceed _llm_min_text_bytes
    with patch.object(tx, "_run_llm_for_extraction", _fake_run):
        tx._extract_llm("super_agent", "s-1", "proj-1", _payload(big_text), provider_kind="gemini")

    assert captured["cmd_template"][0] == "gemini"


def test_extract_llm_disabled_returns_empty(monkeypatch):
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "0")
    with patch.object(tx, "_run_llm_for_extraction") as m:
        out = tx._extract_llm(
            "super_agent", "s-1", "proj-1", _payload("x" * 5000), provider_kind="anthropic"
        )
    assert out == []
    m.assert_not_called()


def test_extract_for_session_passes_provider_to_llm(monkeypatch, isolated_db):
    monkeypatch.setenv("AGENTED_TAKEAWAY_PROVIDER", "openai")
    seen = {}

    def _fake_llm(sk, sid, pid, payload, *, provider_kind="anthropic", model_override=None):
        seen["provider_kind"] = provider_kind
        return []

    fake_payload = SessionPayload(
        text="x" * 5000, backend_type="claude", project_id="proj-1", outcome="completed"
    )
    with (
        patch.object(tx, "_FETCHERS", {"super_agent": lambda _id: fake_payload}),
        patch.object(tx, "_extract_heuristic", lambda *a, **k: []),
        patch.object(tx, "_extract_llm", _fake_llm),
    ):
        tx.extract_for_session("super_agent", "s-1", project_id="proj-1")

    assert seen["provider_kind"] == "openai"


def test_default_provider_kind_falls_back_to_anthropic(monkeypatch):
    monkeypatch.delenv("AGENTED_TAKEAWAY_PROVIDER", raising=False)
    assert tx._default_provider_kind("proj-1") == "anthropic"


def test_extract_for_session_explicit_provider_overrides_env(monkeypatch, isolated_db):
    monkeypatch.setenv("AGENTED_TAKEAWAY_PROVIDER", "openai")
    seen = {}

    def _fake_llm(sk, sid, pid, payload, *, provider_kind="anthropic", model_override=None):
        seen["provider_kind"] = provider_kind
        return []

    fake_payload = SessionPayload(
        text="x" * 5000, backend_type="claude", project_id="proj-1", outcome="completed"
    )
    with (
        patch.object(tx, "_FETCHERS", {"super_agent": lambda _id: fake_payload}),
        patch.object(tx, "_extract_heuristic", lambda *a, **k: []),
        patch.object(tx, "_extract_llm", _fake_llm),
    ):
        tx.extract_for_session("super_agent", "s-1", project_id="proj-1", provider_kind="gemini")
    assert seen["provider_kind"] == "gemini"


# ---------------------------------------------------------------------------
# Regression: invalid provider-kind must not discard heuristic takeaways
# ---------------------------------------------------------------------------


def test_invalid_env_provider_preserves_heuristic_takeaways(monkeypatch, isolated_db):
    """A bad AGENTED_TAKEAWAY_PROVIDER must NOT discard heuristic takeaways.

    Fix 2 (_default_provider_kind validation) falls back to "anthropic".
    Fix 1 (_extract_llm ValueError catch) ensures even a direct invalid
    provider_kind passed to _extract_llm returns [] rather than raising.
    The combination means heuristic takeaways are always persisted.
    """
    monkeypatch.setenv("AGENTED_TAKEAWAY_PROVIDER", "not-a-provider")

    fake_payload = SessionPayload(
        text="x" * 5000, backend_type="claude", project_id="proj-1", outcome="completed"
    )

    heuristic_item = {
        "session_kind": "super_agent",
        "session_id": "s-1",
        "project_id": "proj-1",
        "kind": "domain_fact",
        "content": "X",
        "confidence": 0.9,
        "evidence": {"extractor": "heuristic", "pattern": "test"},
        "suggested_target": None,
        "suggested_payload": None,
        "extractor_version": tx.EXTRACTOR_VERSION,
    }

    with (
        patch.object(tx, "_FETCHERS", {"super_agent": lambda _id: fake_payload}),
        patch.object(tx, "_extract_heuristic", lambda *a, **k: [heuristic_item]),
        # _extract_llm returns [] (simulating LLM not available / disabled)
        patch.object(tx, "_extract_llm", lambda *a, **k: []),
        patch.object(tx.repo, "insert_many", lambda items: ["tk-1"]),
    ):
        ids = tx.extract_for_session("super_agent", "s-1", project_id="proj-1")

    assert ids == ["tk-1"], "heuristic takeaway survived despite invalid AGENTED_TAKEAWAY_PROVIDER"


def test_default_provider_kind_rejects_invalid_env(monkeypatch):
    """_default_provider_kind must fall back to anthropic for unknown env values."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_PROVIDER", "bogus")
    assert tx._default_provider_kind("proj-1") == "anthropic"


def test_extract_llm_catches_valueerror_from_resolve(monkeypatch):
    """resolve_llm_cmd ValueError for unknown provider_kind is caught inside _extract_llm."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    big_text = "x" * 5000

    # Pass an invalid provider_kind directly — resolve_llm_cmd raises ValueError
    result = tx._extract_llm(
        "super_agent", "s-1", "proj-1", _payload(big_text), provider_kind="not-a-real-provider"
    )
    assert result == []
