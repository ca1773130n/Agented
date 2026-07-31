"""Tests for the lightweight turn classifier (19-02).

Covers the keyword-deterministic path, the conversational path, the LLM
fallback for ambiguous turns, the per-backend-kind model selection (house
rule: never claude-only), and safe degradation on LLM error.
"""

import sys
import types

import pytest

from app.services import turn_classifier_service
from app.services.turn_classifier_service import GRD_COMMAND_MAP, classify_turn

# An ambiguous turn: >threshold tokens, no task keyword, no conversational
# opener -> keyword confidence 0.0 -> triggers the LLM fallback.
AMBIGUOUS_TURN = "the encoder situation seems somewhat off lately"


# ---------------------------------------------------------------------------
# Keyword-deterministic path (no LLM call)
# ---------------------------------------------------------------------------


def test_keyword_generic_task_maps_to_quick():
    result = classify_turn("implement the resolver", backend_kind="claude")
    assert result["shape"] == "task"
    assert result["grd_command"] == "/grd:quick"
    assert result["grd_command"] == GRD_COMMAND_MAP["generic"]


def test_keyword_research_maps_to_research():
    result = classify_turn("research RoPE variants", backend_kind="claude")
    assert result["shape"] == "task"
    assert result["grd_command"] == "/grd:research"


def test_keyword_plan_maps_to_plan_phase():
    result = classify_turn("plan phase 20", backend_kind="claude")
    assert result["shape"] == "task"
    assert result["grd_command"] == "/grd:plan-phase"


@pytest.mark.parametrize("text", ["what does this do?", "why?", "how does it work"])
def test_conversational_turns(text):
    result = classify_turn(text, backend_kind="claude")
    assert result["shape"] == "conversational"
    assert result["grd_command"] is None


def test_keyword_clear_turn_makes_no_llm_call(monkeypatch):
    """A keyword-clear turn must never reach litellm.completion."""

    def _boom(*args, **kwargs):
        raise AssertionError("litellm.completion should not be called for keyword-clear turns")

    fake_litellm = types.SimpleNamespace(completion=_boom)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    result = classify_turn("build the new pipeline", backend_kind="claude")
    assert result["shape"] == "task"


# ---------------------------------------------------------------------------
# LLM fallback + per-backend-kind model selection
# ---------------------------------------------------------------------------


class _Spy:
    """Records the model passed to litellm.completion and returns a canned task."""

    def __init__(self, shape="task", intent="generic"):
        self.calls = []
        self._payload = f'{{"shape": "{shape}", "intent": "{intent}"}}'

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        msg = types.SimpleNamespace(content=self._payload)
        choice = types.SimpleNamespace(message=msg)
        return types.SimpleNamespace(choices=[choice])


def _install_spy(monkeypatch, spy):
    fake_litellm = types.SimpleNamespace(completion=spy.completion)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)


def test_ambiguous_turn_invokes_llm_fallback(monkeypatch):
    spy = _Spy(shape="task", intent="generic")
    _install_spy(monkeypatch, spy)

    result = classify_turn(AMBIGUOUS_TURN, backend_kind="claude")

    assert len(spy.calls) == 1
    assert result["shape"] == "task"
    assert result["grd_command"] == "/grd:quick"


def test_model_override_wins_when_set(monkeypatch):
    spy = _Spy()
    _install_spy(monkeypatch, spy)

    classify_turn(AMBIGUOUS_TURN, backend_kind="claude", model_override="custom/model-x")

    assert spy.calls[0]["model"] == "custom/model-x"


@pytest.mark.parametrize("backend_kind", ["claude", "codex", "gemini"])
def test_per_kind_default_model_not_constant_claude(monkeypatch, backend_kind):
    """Each backend_kind selects its own default model (no claude-only default)."""
    spy = _Spy()
    _install_spy(monkeypatch, spy)

    classify_turn(AMBIGUOUS_TURN, backend_kind=backend_kind)

    used_model = spy.calls[0]["model"]
    expected = turn_classifier_service.DEFAULT_MODELS[backend_kind]
    assert used_model == expected
    if backend_kind != "claude":
        assert used_model != turn_classifier_service.DEFAULT_MODELS["claude"]


def test_per_kind_defaults_are_distinct_across_kinds(monkeypatch):
    """The codex/gemini defaults must differ from claude's (asserts the matrix)."""
    seen = {}
    for kind in ("claude", "codex", "gemini"):
        spy = _Spy()
        _install_spy(monkeypatch, spy)
        classify_turn(AMBIGUOUS_TURN, backend_kind=kind)
        seen[kind] = spy.calls[0]["model"]

    assert seen["gemini"] != seen["claude"]
    assert seen["codex"] != seen["claude"]


# ---------------------------------------------------------------------------
# Safe degradation
# ---------------------------------------------------------------------------


def test_llm_error_degrades_to_conversational(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("llm exploded")

    fake_litellm = types.SimpleNamespace(completion=_raise)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)

    result = classify_turn(AMBIGUOUS_TURN, backend_kind="claude")

    assert result["shape"] == "conversational"
    assert result["grd_command"] is None


# ---------------------------------------------------------------------------
# Word-boundary matching — substrings of task keywords must not misroute
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # "explain" contains "plan"; must stay conversational, not /grd:plan-phase.
        "explain how the resolver works",
        "can you explain the routing precedence here",
        # "address" contains "add" — conversational opener "what" wins.
        "what does this address?",
    ],
)
def test_task_keyword_substrings_do_not_misroute(text):
    result = classify_turn(text, backend_kind="claude")
    assert result["shape"] == "conversational"
    assert result["grd_command"] is None


def test_multiword_phrases_still_match():
    result = classify_turn("break down the migration into milestones", backend_kind="claude")
    assert result["shape"] == "task"
    assert result["grd_command"] == "/grd:plan-phase"
