"""Phase E2 — KG signal gathering service.

Queries the compiled Tesserae knowledge graph with a SMALL bounded set of
discovery questions and turns each prose answer into a weighted, deduped
``KGSignalItem``. Signals decay with age (so stale guidance surfaces less
loudly) and are flagged when they overlap an already-forged primitive.

This service is best-effort and NEVER raises: any failure (Tesserae not
enabled, a single ``ask`` shell-out failing, an unexpected error) degrades
gracefully to fewer / zero signals.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

from app.db.harness_kg_signals import first_seen_at_for, record_signal
from app.models.harness_evolution import KGSignalItem
from app.services.tesserae_integration import (
    ask_tesserae,
    context_tesserae,
    get_distill_enabled,
    get_tesserae_root,
)

logger = logging.getLogger(__name__)

W_MAX = 0.7
W_MIN = 0.3
HALF_LIFE_DAYS = 30.0
# SQLite stores space-separated timestamps (NOT 'T') — this matters.
_TS_FMT = "%Y-%m-%d %H:%M:%S"

_DISCOVERY_QUESTIONS = (
    "What recurring problems, mistakes, or decisions appear across this "
    "project's past sessions that are NOT yet codified as a rule, hook, or "
    "command? List each as one concise actionable item.",
    "What domain conventions or procedures recur across the project's code "
    "and docs that a reusable skill should capture? List each concisely.",
    "Given recent session failures, what single most impactful guardrail "
    "(rule or hook) is currently missing?",
)

_WS_RE = re.compile(r"\s+")


def _norm(text: str) -> str:
    """Lower-case, collapse whitespace runs to single spaces, strip."""
    return _WS_RE.sub(" ", text.lower()).strip()


def _now() -> str:
    """Current UTC time formatted with ``_TS_FMT`` (single source)."""
    return datetime.now(timezone.utc).strftime(_TS_FMT)


def _compute_signal_id(project_id: str, question: str, content: str) -> str:
    payload = f"{project_id}\x00{question}\x00{_norm(content)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_weight(first_seen_at: str, now: str) -> float:
    """Exponential decay on the AGE since first sighting.

    Unparseable timestamps fail toward surfacing (return ``W_MAX``). Negative
    ages from clock skew clamp to 0. Result is clamped into [W_MIN, W_MAX].
    """
    try:
        first_dt = datetime.strptime(first_seen_at, _TS_FMT)
        now_dt = datetime.strptime(now, _TS_FMT)
    except (ValueError, TypeError):
        logger.warning(
            "harness_kg_signals: compute_weight could not parse timestamps "
            "(first_seen_at=%r now=%r); defaulting weight to W_MAX",
            first_seen_at,
            now,
        )
        return W_MAX
    age_days = max(0.0, (now_dt - first_dt).total_seconds() / 86400.0)
    w = W_MAX * (2 ** (-age_days / HALF_LIFE_DAYS))
    return min(W_MAX, max(W_MIN, w))


def _is_already_forged(content_norm: str, forged_index: list[str] | None) -> bool:
    """True if any forged primitive content overlaps the signal.

    Conservative: only a >=60-char contiguous slice of the shorter string
    appearing in the longer one (or the whole shorter string contained in the
    longer one) counts. Tiny / empty strings are skipped to avoid false
    positives.
    """
    if not content_norm or not forged_index:
        return False
    for c in forged_index:
        cn = _norm(c)
        if not cn:
            continue
        shorter, longer = (cn, content_norm) if len(cn) <= len(content_norm) else (content_norm, cn)
        if len(shorter) < 60:
            continue
        if shorter in longer or shorter[:60] in longer:
            return True
    return False


def gather_kg_signals(
    project_id: str,
    *,
    forged_index: list[str] | None = None,
    now: str | None = None,
) -> list[KGSignalItem]:
    """Query Tesserae with bounded discovery questions; return weighted signals.

    Best-effort: never raises. Returns ``[]`` when Tesserae is not enabled for
    the project or on any unexpected error.
    """
    try:
        root = get_tesserae_root(project_id)
        if root is None:
            return []
        now = now or _now()
        # When distillation is on, retrieve via multi-pool `context` so the
        # distilled Runbook/Gotcha/Event pools enter the signal corpus;
        # otherwise keep the plain `ask` path.
        distill = get_distill_enabled(project_id)
        results: list[KGSignalItem] = []
        for q in _DISCOVERY_QUESTIONS:
            try:
                ans = (
                    context_tesserae(project_id, q, multi_pool=True)
                    if distill
                    else ask_tesserae(project_id, q, top_k=5)
                )
            except Exception:
                logger.warning("tesserae query failed for a discovery question", exc_info=True)
                continue
            if not ans:
                continue
            # A single bad write/parse skips only that signal, not the round.
            try:
                content = (ans or "").strip()
                if not content:
                    continue
                cn = _norm(content)
                sid = _compute_signal_id(project_id, q, content)
                first = first_seen_at_for(sid) or now
                w = compute_weight(first, now)
                forged = _is_already_forged(cn, forged_index)
                if forged:
                    w = W_MIN
                record_signal(
                    signal_id=sid,
                    project_id=project_id,
                    question=q,
                    content=content,
                    weight=w,
                    already_forged=forged,
                    now=now,
                )
                results.append(
                    KGSignalItem(
                        signal_id=sid,
                        project_id=project_id,
                        question=q,
                        content=content,
                        weight=w,
                        already_forged=forged,
                        first_seen_at=first,
                        captured_at=now,
                    )
                )
            except Exception:
                logger.warning("failed to record a KG signal; skipping it", exc_info=True)
                continue
        return results
    except Exception:
        logger.warning("gather_kg_signals failed unexpectedly", exc_info=True)
        return []
