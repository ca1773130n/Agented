"""Lightweight turn classifier for the GRD default-driver funnel.

Splits a chat turn into a *task*-shaped turn (which spawns a GRD PSM session)
versus a *conversational* turn (which stays on cliproxy), and maps task turns to
the correct ``/grd:`` command.

Pipeline SHAPE mirrors ``SketchRoutingService.classify``:
``keyword score -> (optional cache) -> LLM fallback -> deterministic fallback``.
The turn keyword seeds here are turn-specific (NOT imported from the sketch
domain). The LLM fallback honors ``{backend_kind, model_override}`` with a
per-kind default model and NEVER hardcodes a claude default (house rule:
feedback_llm_features_support_all_backends).
"""

import logging
from typing import Dict, Optional, Set

from ..utils.llm_json import extract_json_object

logger = logging.getLogger(__name__)


# =============================================================================
# Turn-specific keyword seeds (intent buckets)
# =============================================================================

TASK_RESEARCH: Set[str] = {
    "research",
    "investigate",
    "survey",
    "compare papers",
    "literature",
}

TASK_PLAN: Set[str] = {
    "plan",
    "roadmap",
    "phase",
    "break down",
    "milestone",
}

TASK_GENERIC: Set[str] = {
    "build",
    "implement",
    "fix",
    "add",
    "refactor",
    "run",
    "create",
    "test",
}

# Conversational signals: question/explanatory openers.
CONVERSATIONAL: Set[str] = {
    "what",
    "why",
    "how",
    "explain",
    "?",
}

# Turns at or under this token count with no strong task signal are treated as
# conversational (mirrors the "short/question turn" heuristic).
CONVERSATIONAL_TOKEN_THRESHOLD = 3

# Intent bucket -> GRD command.
GRD_COMMAND_MAP: Dict[str, str] = {
    "research": "/grd:research",
    "plan": "/grd:plan-phase",
    "generic": "/grd:quick",
}

# Per-backend-kind default model for the LLM fallback. NEVER a hardcoded
# claude-only default — every supported kind resolves to its own small model.
DEFAULT_MODELS: Dict[str, str] = {
    "claude": "openai/claude-haiku-4-5-20251001",
    "codex": "openai/gpt-4o-mini",
    # gemini backend = Google Antigravity; gemini-1.5 is long obsolete. LLM
    # classification is best-effort (graceful keyword fallback) if litellm can't
    # resolve the current id.
    "gemini": "gemini/gemini-3-flash-preview",
    "opencode": "openai/gpt-4o-mini",
}

# Generic cross-kind fallback when an unknown backend_kind is passed.
GENERIC_DEFAULT_MODEL = "openai/gpt-4o-mini"

# Mirror SketchRoutingService.KEYWORD_CONFIDENCE_THRESHOLD.
KEYWORD_CONFIDENCE_THRESHOLD = 0.6


def _resolve_model(backend_kind: str, model_override: Optional[str]) -> str:
    """Resolve the LLM model from ``{backend_kind, model_override}``.

    ``model_override`` wins when set; otherwise a per-kind default is selected.
    NEVER returns a hardcoded claude default for non-claude kinds.
    """
    if model_override:
        return model_override
    return DEFAULT_MODELS.get(backend_kind, GENERIC_DEFAULT_MODEL)


def _keyword_classify(text: str) -> dict:
    """Score-based turn keyword classification.

    Returns ``{"shape", "intent", "confidence"}``. Intent is one of
    ``research|plan|generic|conversational``.
    """
    lowered = text.lower()
    tokens = lowered.split()
    # Word set with surrounding punctuation stripped, so openers like "what"
    # match the token "what?" but NOT a substring of "somewhat".
    word_set = {tok.strip("?.!,;:") for tok in tokens}

    # Task keywords match on word boundary too — "explain" must not score the
    # keyword "plan", "address" must not score "add". Multi-word phrases
    # ("break down", "compare papers") can't appear in the word set, so they
    # keep the substring check.
    def _score(keywords) -> int:
        return sum(1 for kw in keywords if (kw in lowered if " " in kw else kw in word_set))

    research_score = _score(TASK_RESEARCH)
    plan_score = _score(TASK_PLAN)
    generic_score = _score(TASK_GENERIC)
    # Conversational openers match on word boundary (token membership); "?" is
    # punctuation so it stays a substring check.
    conversational_score = sum(
        1
        for kw in CONVERSATIONAL
        if (kw == "?" and "?" in lowered) or (kw != "?" and kw in word_set)
    )

    task_scores = {
        "research": research_score,
        "plan": plan_score,
        "generic": generic_score,
    }
    best_intent = max(task_scores, key=task_scores.get)
    best_task_score = task_scores[best_intent]

    # A clear task keyword (>=1 match) clears the threshold deterministically.
    if best_task_score >= 1:
        return {"shape": "task", "intent": best_intent, "confidence": 1.0}

    # Short / question-shaped turns with no task signal -> conversational.
    if conversational_score >= 1 or len(tokens) <= CONVERSATIONAL_TOKEN_THRESHOLD:
        return {"shape": "conversational", "intent": "conversational", "confidence": 1.0}

    # No strong signal either way -> ambiguous (triggers LLM fallback).
    return {"shape": "conversational", "intent": "conversational", "confidence": 0.0}


def _llm_classify(text: str, *, backend_kind: str, model_override: Optional[str]) -> Optional[dict]:
    """LLM tiebreak for ambiguous turns, with graceful fallback.

    Invoked with the resolved model from ``{backend_kind, model_override}``,
    mirroring ``SketchRoutingService._llm_classify`` call shape. Returns a
    classification dict or ``None`` on any failure (caller degrades safely).
    """
    try:
        import litellm
    except ImportError:
        logger.debug("litellm not available, skipping LLM turn classification")
        return None

    model = _resolve_model(backend_kind, model_override)

    system_prompt = (
        "You classify a single chat turn for a coding assistant.\n"
        "Decide whether the turn is a concrete software TASK or a "
        "CONVERSATIONAL question/comment.\n"
        "If a task, pick an intent: 'research', 'plan', or 'generic'.\n"
        "If conversational, intent is 'conversational'.\n\n"
        "Respond with ONLY a JSON object, no other text:\n"
        '{"shape": "task"|"conversational", "intent": "research"|"plan"|"generic"|"conversational"}'
    )

    try:
        api_base = None
        try:
            from .cliproxy_manager import CLIProxyManager

            api_base = CLIProxyManager.get_base_url()
        except Exception:
            pass  # Intentionally silenced: non-critical.

        logger.info("Using LLM model %s for turn classification (kind=%s)", model, backend_kind)

        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Classify this turn:\n\n{text}"},
            ],
            "timeout": 5,
            "api_key": "not-needed",
        }
        if api_base:
            kwargs["api_base"] = api_base

        response = litellm.completion(**kwargs)
        # An empty / prose / fenced LLM reply is an expected outcome (the proxy
        # may return nothing or wrap the object): extract the JSON object and
        # fall back to keyword classification silently rather than crashing
        # json.loads (or .strip() on a None body) on every call.
        result = extract_json_object(response.choices[0].message.content)
        if result is None:
            logger.debug("LLM turn classification returned no JSON body; falling back")
            return None

        if "shape" not in result or "intent" not in result:
            logger.warning("LLM turn classification missing keys: %s", result)
            return None

        return {"shape": result["shape"], "intent": result["intent"]}

    except Exception as e:
        logger.warning("LLM turn classification failed: %s", e)
        return None


def classify_turn(text: str, *, backend_kind: str, model_override: Optional[str] = None) -> dict:
    """Classify a chat turn into task vs conversational + map to a GRD command.

    Pipeline: keyword (threshold-gated at 0.6) -> LLM fallback -> deterministic
    conversational fallback. The LLM fallback is parameterized by
    ``{backend_kind, model_override}`` and never hardcodes claude.

    Returns ``{"shape": "task"|"conversational", "grd_command": str|None,
    "intent": str}``.
    """
    keyword_result = _keyword_classify(text)

    if keyword_result["confidence"] >= KEYWORD_CONFIDENCE_THRESHOLD:
        intent = keyword_result["intent"]
        return {
            "shape": keyword_result["shape"],
            "grd_command": GRD_COMMAND_MAP.get(intent),
            "intent": intent,
        }

    # Ambiguous -> LLM tiebreak.
    llm_result = _llm_classify(text, backend_kind=backend_kind, model_override=model_override)
    if llm_result is not None:
        intent = llm_result["intent"]
        shape = llm_result["shape"]
        return {
            "shape": shape,
            "grd_command": GRD_COMMAND_MAP.get(intent) if shape == "task" else None,
            "intent": intent,
        }

    # Deterministic safe fallback: treat as conversational.
    return {"shape": "conversational", "grd_command": None, "intent": "conversational"}
