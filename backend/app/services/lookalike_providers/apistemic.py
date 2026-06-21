"""ApistemicProvider — the one concrete ``apistemic`` market-lookalike adapter
(phase 27, plan 02).

Wires the 27-01 ``LookalikeProvider`` seam to Apistemic's RapidAPI listing
(research [14]: domain seed -> competitors/lookalikes, $0-$499/mo). The adapter
is **inert until ``APISTEMIC_API_KEY`` is set** — the EXACT
``github_repo.has_credential`` GITHUB_TOKEN-or-skip discipline: with no key
``is_configured()`` is ``False`` and ``find_lookalikes`` short-circuits to
``outcome='not_configured'`` and makes ZERO network calls (the BUY gate — never
an unauth call to a paid endpoint, never fake data, never a crash).

``find_lookalikes`` NEVER raises (the ``job_board.fetch`` discipline): every
transport/HTTP/parse path collapses to a tagged outcome —

    | condition                              | outcome          |
    |----------------------------------------|------------------|
    | ``is_configured()`` False              | ``not_configured`` |
    | seed has no resolvable domain          | ``error``        |
    | ``httpx.HTTPError`` (DNS/timeout/conn) | ``error``        |
    | 401 / 403 (bad/expired key)            | ``not_configured`` |
    | 429 (rate limit)                       | ``throttled``    |
    | other non-200                          | ``error``        |
    | malformed JSON body                    | ``error``        |
    | 200 with parseable body                | ``ok``           |

``_normalize`` is the ``job_board._normalize_postings`` defensive-parse: every
field ``.get()``-guarded, a candidate with no usable url/domain dropped, the
seed domain itself excluded, NEVER raises on a shape mismatch — worst case is
``[]`` (an empty review queue), never a 500.

# UNTESTED — configured-when-keyed seam
# ------------------------------------------------------------------------------
# We hold NO Apistemic account to dogfood the live request/response, so the two
# things below are the DOCUMENTED-BUT-UNVERIFIED guess (research [14] verified
# capability + pricing, NOT the exact JSON). They are the ONLY thing a future
# engineer with a key adjusts against a real response (the P4 auto-implement
# seam posture: built + gated, not dogfooded):
#   1. ``_LOOKALIKE_ENDPOINT`` — the request path under ``APISTEMIC_BASE``.
#   2. ``_normalize`` — the response field map (which keys carry the url / name /
#      score / reason). It already tries several documented key names defensively,
#      so a mismatch degrades to ``[]`` rather than a crash.
# Everything else (the key gate, the never-raise outcome mapping, the no-call
# invariant) is verified by ``tests/test_apistemic_provider.py`` with ZERO live
# network. Ruff line-length=100 / py310.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import httpx

from app.services.lookalike_providers import registry
from app.services.lookalike_providers.base import Candidate, LookalikeResult

logger = logging.getLogger(__name__)

# Env var that holds the RapidAPI key. UNSET -> ``not_configured``, the BUY gate
# (mirrors ``github_repo``'s GITHUB_TOKEN-or-skip credential seam). No key ->
# the paid endpoint is NEVER called.
APISTEMIC_API_KEY_ENV = "APISTEMIC_API_KEY"

# RapidAPI listing host (research [14]). The X-RapidAPI-Host header must match.
APISTEMIC_BASE = "https://apistemic.p.rapidapi.com"
_RAPIDAPI_HOST = "apistemic.p.rapidapi.com"

# # UNTESTED — configured-when-keyed seam: the request path is the documented
# guess. A future engineer with a key adjusts this against the real API.
_LOOKALIKE_ENDPOINT = f"{APISTEMIC_BASE}/v1/lookalikes"

# HTTP timeout for one lookalike lookup (seconds). Short — a single read.
_TIMEOUT = 15

# # UNTESTED — configured-when-keyed seam: documented-but-unverified payload
# keys. ``_normalize`` tries each defensively (``.get()``-guarded), so a mismatch
# degrades to ``[]`` rather than crashing. Adjust against a real response.
_RESULT_KEYS = ("results", "competitors", "lookalikes", "data")
_URL_KEYS = ("url", "website", "domain", "homepage")
_NAME_KEYS = ("name", "title", "company", "company_name")
_SCORE_KEYS = ("score", "similarity", "confidence")
_REASON_KEYS = ("reason", "why", "description", "summary")


def _extract_domain(seed: str) -> str:
    """Return the bare host of ``seed`` (``www.`` stripped), or ``""``.

    Pure, no I/O, never raises. A scheme-bearing URL is parsed for its netloc; a
    bare host (no ``://``) is treated as the host itself. An empty/garbage seed
    yields ``""`` so the caller returns ``outcome='error'`` instead of calling
    the API with a junk domain.
    """
    raw = (seed or "").strip()
    if not raw:
        return ""
    # urlparse only populates ``netloc`` when a scheme (``//``) is present; a bare
    # ``acme.com`` lands in ``path``. Synthesize a scheme so the host parses.
    parsed = urlparse(raw if "//" in raw else f"//{raw}")
    host = (parsed.hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _coerce_str(value: object) -> str:
    """Best-effort ``str`` of a payload value; non-str/None -> ``""``."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _coerce_score(value: object) -> float | None:
    """Coerce a score field to ``float`` or ``None`` (NULL-accepting).

    A missing/odd score NEVER blocks a candidate (the ``Candidate.score``
    NULL-safe contract) — it just comes back ``None``.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_absolute_url(raw_url: str) -> tuple[str, str]:
    """Return ``(absolute_url, host)`` for a candidate's url/domain field.

    A bare domain (no scheme) is promoted to ``https://<domain>``. Returns
    ``("", "")`` when no usable host can be derived — the caller drops the item.
    Never raises.
    """
    value = (raw_url or "").strip()
    if not value:
        return "", ""
    host = _extract_domain(value)
    if not host:
        return "", ""
    absolute = value if "//" in value else f"https://{value}"
    return absolute, host


def _normalize(payload: object, seed_domain: str, *, limit: int) -> list[Candidate]:
    """Map an Apistemic payload to ``Candidate`` rows — DEFENSIVE.

    The ``job_board._normalize_postings`` discipline: accept a JSON list OR a
    dict carrying a results array under one of ``_RESULT_KEYS``; every field is
    ``.get()``-guarded; an item with no usable url/domain is DROPPED; the seed
    domain itself is excluded; a missing score becomes ``None``. NEVER raises on
    a missing/odd field — worst case returns ``[]``. Capped to ``limit``.

    # UNTESTED — configured-when-keyed seam: the field map (``_*_KEYS``) is the
    # documented guess. A real-response mismatch degrades here to ``[]``.
    """
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = []
        for key in _RESULT_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
    else:
        items = []

    candidates: list[Candidate] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        raw_url = ""
        for key in _URL_KEYS:
            raw_url = _coerce_str(item.get(key))
            if raw_url:
                break
        url, host = _to_absolute_url(raw_url)
        if not url:
            # No usable url/domain — drop it (can't be a review-queue row).
            continue
        if seed_domain and host == seed_domain:
            # Never include the seed company in its own lookalikes.
            continue

        name = ""
        for key in _NAME_KEYS:
            name = _coerce_str(item.get(key))
            if name:
                break
        if not name:
            name = host  # fall back to the host so the chip is never blank.

        score = None
        for key in _SCORE_KEYS:
            if key in item:
                score = _coerce_score(item.get(key))
                break

        reason = ""
        for key in _REASON_KEYS:
            reason = _coerce_str(item.get(key))
            if reason:
                break
        if not reason:
            reason = "Apistemic lookalike"

        candidates.append(
            Candidate(
                url=url,
                name=name,
                score=score,
                evidence={"provider": "apistemic", "reason": reason, "domain": host},
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


class ApistemicProvider:
    """Key-gated ``apistemic`` lookalike provider (the 27-01 Protocol).

    Inert until ``APISTEMIC_API_KEY`` is set: ``is_configured()`` False ->
    ``find_lookalikes`` returns ``not_configured`` and makes ZERO network calls
    (the BUY gate). With the key set it GETs the RapidAPI listing endpoint and
    maps every outcome through ``_normalize`` — NEVER raising.
    """

    name = "apistemic"

    def is_configured(self) -> bool:
        """True only when ``APISTEMIC_API_KEY`` is set (and non-blank).

        The EXACT ``github_repo.has_credential`` discipline — no key -> the paid
        endpoint is never called. Never raises.
        """
        return bool((os.environ.get(APISTEMIC_API_KEY_ENV) or "").strip())

    def find_lookalikes(self, seed: str, *, limit: int = 20) -> LookalikeResult:
        """One read-only lookalike lookup of ``seed``; tagged result; never raises.

        Re-checks ``is_configured()`` (defensive — the caller also gates) and
        short-circuits to ``not_configured`` with NO httpx call when the key is
        unset. Otherwise GETs ``_LOOKALIKE_ENDPOINT`` and maps every
        transport/HTTP/parse outcome to a tag; only a 200 with a parseable body
        is ``ok``.
        """
        # The BUY gate: no key -> never the paid call, never fake data.
        if not self.is_configured():
            return LookalikeResult(outcome="not_configured", detail="APISTEMIC_API_KEY unset")

        domain = _extract_domain(seed)
        if not domain:
            return LookalikeResult(outcome="error", detail="seed has no resolvable domain")

        try:
            resp = httpx.get(
                _LOOKALIKE_ENDPOINT,
                params={"domain": domain, "limit": limit},
                headers={
                    "X-RapidAPI-Key": os.environ[APISTEMIC_API_KEY_ENV],
                    "X-RapidAPI-Host": _RAPIDAPI_HOST,
                },
                timeout=_TIMEOUT,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            # Transport error (DNS / timeout / connection) — never propagates.
            logger.warning("apistemic transport error for domain %s", domain, exc_info=True)
            return LookalikeResult(outcome="error", detail="apistemic transport error")

        status = resp.status_code

        # Bad/expired key — surface as the BUY gate, not a hard error.
        if status in (401, 403):
            logger.warning("apistemic rejected the key (HTTP %d)", status)
            return LookalikeResult(outcome="not_configured", detail="apistemic rejected the key")

        # Rate limit — transient; the surface degrades past it.
        if status == 429:
            logger.warning("apistemic throttled (HTTP 429)")
            return LookalikeResult(outcome="throttled", detail="apistemic rate limited")

        if status != 200:
            logger.warning("apistemic unexpected HTTP %d", status)
            return LookalikeResult(outcome="error", detail=f"apistemic HTTP {status}")

        try:
            payload = resp.json()
        except (ValueError, TypeError):
            logger.warning("apistemic malformed JSON body")
            return LookalikeResult(outcome="error", detail="apistemic malformed JSON")

        return LookalikeResult(outcome="ok", candidates=_normalize(payload, domain, limit=limit))


# Register on import (the package __init__ imports this module). Last-write-wins.
registry.register(ApistemicProvider())
