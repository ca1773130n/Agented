"""DiscoveryService — on-demand competitor-discovery scan orchestration (Phase 24).

The operator-visible flow that wires the discovery brain together (the service
the 24-04 routes call):

  * **24-01** persistence — ``app.db.discovery_suggestions`` (the ``dsug-`` DAO:
    ``upsert_suggestion`` / ``list_suggestions`` / ``get_suggestion`` /
    ``set_status``). Re-scans UPSERT; an operator's add/dismiss verdict is sticky.
  * **24-02** similarity + ranking — ``GitHubSimilarityClient`` (S1 shared-topic +
    S2 stargazer overlap on the authenticated PAT seam) and the deterministic
    ``discovery_ranker`` (weighted, renormalized-over-active, explainable blend).
  * **P1 hook** — ``CompetitorSourceService.list_sources`` reads the project's
    seeds; ``add_source(..., origin='discovery')`` is the promote hook (NO
    signature change).

``scan_project`` turns a project's watched ``kind=='github_repo'`` seeds into
ranked, de-duped, persisted ``discovery_suggestion`` rows; ``promote_suggestion``
turns a suggestion into a watched ``competitor_source``; ``dismiss_suggestion``
flips its status.

README lens (design §"README/infra lens") is an **optional re-rank signal** that
degrades ``embedding -> text -> off`` and NEVER blocks the scan:

  * ``embedding`` — when ``embedding_service.is_available()``: embed the seed and
    candidate READMEs and cosine-match them (the ``repeated_request_detector``
    ``embed_texts`` + ``cosine_similarity_batch`` precedent). If the embedding lib
    is absent at call time ``embed_texts`` returns ``[]`` → we fall back to text.
  * ``text`` — a cheap stdlib ``difflib.SequenceMatcher`` ratio (no model needed).
  * ``off`` — the README signal is simply absent; the ranker renormalizes over
    only the active signals so "off" never penalizes a candidate (24-02 contract).

Cost note for 24-04: the GitHub fan-out (S1 + S2 + README fetches) is HEAVY and
read-only. ``scan_project`` is the heavy method — the route layer (24-04) MUST
keep it OFF the request path (background task / ``sync_to_thread``) or bound it.
No LLM here; the ranker is deterministic and the README similarity is numeric.
"""

from __future__ import annotations

import base64
import binascii
import difflib
import logging
from typing import Optional

import httpx

from app.db import discovery_suggestions
from app.services import discovery_ranker, embedding_service
from app.services.competitor_source_service import CompetitorSourceService
from app.services.github_similarity_client import GitHubSimilarityClient

logger = logging.getLogger(__name__)


class PromotionConflict(Exception):
    """A suggestion cannot be promoted from its current status (e.g. dismissed).

    Distinct from ``ValueError`` (unknown / foreign-project id → 404) so the route
    can map a status conflict to a 409 instead. Raised by
    :meth:`DiscoveryService.promote_suggestion` when an operator accepts a
    ``dismissed`` suggestion — it must be re-suggested before it can be promoted,
    not silently resurrected.
    """


# README-lens resolution order (design §"README/infra lens"): a real embedding
# backend wins; otherwise a cheap stdlib text-overlap; otherwise the signal is
# simply absent. These are the only three values ``readme_mode`` ever takes.
README_MODE_EMBEDDING = "embedding"
README_MODE_TEXT = "text"
README_MODE_OFF = "off"

# Throttle status codes (secondary / abuse rate limit). Mirrors
# ``GitHubSimilarityClient._THROTTLE_STATUS`` / ``GitHubMonitorService`` — a
# 403/429 means back off, not "no README".
_THROTTLE_STATUS = (403, 429)

# Scan-level fan-out caps (design §"Trigger" — bound the per-scan blast radius).
# A project can watch arbitrarily many ``github_repo`` seeds; each becomes an
# S1+S2 GitHub fan-out, so an unbounded scan could burn the whole PAT budget.
# ``_MAX_SEEDS`` caps how many seeds we actually fan out (the rest are reported
# as truncated); ``_MAX_SCAN_REQUESTS`` is a scan-wide GitHub-request budget /
# circuit-breaker that stops launching further seed fan-outs once tripped.
_MAX_SEEDS = 25
_MAX_SCAN_REQUESTS = 2000

# Worst-case GitHub requests one seed's fan-out can issue: S2 stargazer overlap
# is the dominant term (the similarity client's per-overlap hard cap), plus a
# handful for repo_metadata + the S1 topic searches. Used as a conservative
# estimate to drive the scan-wide ``_MAX_SCAN_REQUESTS`` circuit-breaker without
# plumbing exact counts back from every client method.
_EST_REQUESTS_PER_SEED = 130

# Cap how many top-ranked candidates get a README fetch+similarity pass. Each
# README is a separate GitHub GET, so this bounds the fan-out's tail cost; the
# ranker already trims to the strongest candidates (TOP_N) but the README lens
# only sharpens the head of the list. Unranked candidates keep README absent
# (the renormalizer drops README's weight for them — never a penalty).
_README_CANDIDATE_CAP = 25

# Truncate READMEs before embedding / diffing — the intro carries the signal and
# this bounds both the embed cost and the difflib O(n^2) ratio. Mirrors keeping
# similarity work cheap (repeated_request_detector embeds short request text).
_README_CHARS = 4000

# Short HTTP timeout for a single README GET (seconds) — same budget the
# similarity client uses for its cheap reads.
_README_TIMEOUT = 15.0

# GitHub REST root — same host the similarity client / monitor already talk to.
_API_ROOT = "https://api.github.com"

# Sentinel ``_fetch_readme`` returns on a 403/429 so the README lens can tell a
# throttle ("stop the whole lens, back off") apart from "this repo has no README"
# (``None`` — skip just this candidate). Distinct object identity, never a README.
_README_THROTTLED = object()


class DiscoveryService:
    """Orchestrate a project's competitor-discovery scan (24-01 + 24-02 + P1).

    Stateless: every method is a ``@staticmethod`` keying off ``project_id`` /
    ``suggestion_id`` and the module-level DAO + client + ranker. Persistence is
    the 24-01 raw-SQLite DAO (no new DB code here).
    """

    # -- README-mode resolver -------------------------------------------------

    @staticmethod
    def _resolve_readme_mode(readme_mode: Optional[str] = None) -> str:
        """Resolve the README lens to one of ``{embedding, text, off}``.

        An explicit ``readme_mode`` (a caller / route override) wins when it is a
        known value — in particular ``'off'`` lets a caller skip the README fetch
        entirely. Otherwise auto-resolve: ``embedding`` when the embedding backend
        is available, else the cheap stdlib ``text`` overlap. Auto never returns
        ``'off'`` (text always works); ``'off'`` is an explicit opt-out. NEVER
        raises — a failure to probe the embedding backend degrades to ``text``.
        """
        if readme_mode in (README_MODE_EMBEDDING, README_MODE_TEXT, README_MODE_OFF):
            return readme_mode
        try:
            if embedding_service.is_available():
                return README_MODE_EMBEDDING
        except Exception:  # noqa: BLE001 — probing the backend must never block a scan
            logger.warning("discovery: embedding availability probe failed", exc_info=True)
        return README_MODE_TEXT

    # -- README fetch (read-only, on the shared auth seam) --------------------

    @staticmethod
    def _fetch_readme(owner: str, repo: str):
        """Fetch a repo's README text via the authenticated similarity seam.

        Reuses ``GitHubSimilarityClient._headers()`` (the ONE credential seam) and
        GETs ``repos/{owner}/{repo}/readme``; the default ``Accept`` returns the
        content base64-encoded which we decode to UTF-8 text.

        Returns the README ``str``; ``None`` when the token is unset, the repo has
        no README, GitHub answers a benign non-200, or any transport / decode
        error occurs (skip just this repo); or the ``_README_THROTTLED`` sentinel
        on a 403/429 so the caller stops the README lens and backs off instead of
        burning the rest of the scan's budget (mirroring the similarity-client /
        poll throttle discipline). NEVER raises into the scan.
        """
        headers = GitHubSimilarityClient._headers()
        if headers is None:
            return None
        try:
            resp = httpx.get(
                f"{_API_ROOT}/repos/{owner}/{repo}/readme",
                headers=headers,
                timeout=_README_TIMEOUT,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            logger.warning("discovery: README fetch transport error for %s/%s", owner, repo)
            return None
        if resp.status_code in _THROTTLE_STATUS:
            logger.warning(
                "discovery: README fetch throttled (HTTP %s) for %s/%s — aborting README lens",
                resp.status_code,
                owner,
                repo,
            )
            return _README_THROTTLED
        if resp.status_code != 200:
            return None
        try:
            body = resp.json()
        except (ValueError, TypeError):
            return None
        if not isinstance(body, dict):
            return None
        content = body.get("content")
        if not isinstance(content, str) or not content:
            return None
        try:
            decoded = base64.b64decode(content)
        except (binascii.Error, ValueError):
            return None
        text = decoded.decode("utf-8", errors="replace").strip()
        return text or None

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Cheap stdlib README overlap in ``[0,1]`` — ``difflib.SequenceMatcher``.

        The MVP ``text`` lens: no model, deterministic, bounded by truncating both
        READMEs to ``_README_CHARS``. Empty either side → 0.0.
        """
        if not a or not b:
            return 0.0
        ratio = difflib.SequenceMatcher(None, a[:_README_CHARS], b[:_README_CHARS]).ratio()
        return max(0.0, min(float(ratio), 1.0))

    @classmethod
    def _readme_similarity(
        cls, seed_readme: Optional[str], cand_readme: Optional[str], mode: str
    ) -> Optional[float]:
        """README similarity for one candidate under ``mode`` (``None`` if absent).

        ``embedding``: ``embed_texts([seed, cand])`` + ``cosine_similarity_batch``
        (the ``repeated_request_detector`` pattern). When the embedding lib is
        absent at call time ``embed_texts`` returns ``[]`` → fall back to the
        ``text`` ratio (mirroring the None-degrade contract). ``text``: the
        ``difflib`` ratio. ``off`` / a missing README on either side → ``None`` so
        the ranker drops README's weight from the denominator (never penalizes).
        """
        if mode == README_MODE_OFF or not seed_readme or not cand_readme:
            return None
        seed_text = seed_readme[:_README_CHARS]
        cand_text = cand_readme[:_README_CHARS]
        if mode == README_MODE_EMBEDDING:
            try:
                vectors = embedding_service.embed_texts([seed_text, cand_text])
            except Exception:  # noqa: BLE001 — never block the scan on the embed model
                logger.warning(
                    "discovery: README embed failed; falling back to text", exc_info=True
                )
                vectors = []
            if len(vectors) == 2:
                score = embedding_service.cosine_similarity_batch(vectors[0], [vectors[1]])
                if score:
                    return max(0.0, min(float(score[0]), 1.0))
            # embed_texts returned [] (lib absent) — degrade to the text ratio.
            return cls._text_similarity(seed_text, cand_text)
        # README_MODE_TEXT
        return cls._text_similarity(seed_text, cand_text)

    # -- scan -----------------------------------------------------------------

    @classmethod
    def scan_project(
        cls,
        project_id: str,
        *,
        readme_mode: Optional[str] = None,
        max_seeds: int = _MAX_SEEDS,
        max_requests: int = _MAX_SCAN_REQUESTS,
    ) -> dict:
        """Fan a project's GitHub seeds → similarity → ranker → persisted rows.

        Steps (design §"Trigger" — on-demand only, seeds == ``github_repo``
        sources):

          1. ``seeds`` = the project's ``competitor_source`` rows with
             ``kind=='github_repo'`` (``list_sources`` filtered). No seeds →
             ``{"scanned": 0, ...}`` (no error).
          2. Parse each seed's ``(owner, repo)`` (``parse_seed``) → the
             ``existing_watched`` set, used to EXCLUDE already-watched candidates.
          3. Cap the fan-out: scan at most ``max_seeds`` parsed seeds, and stop
             launching further seed fan-outs once the running request estimate
             would exceed the scan-wide ``max_requests`` budget (circuit-breaker).
             For each scanned seed (try/except per seed — one bad seed never
             aborts the whole scan): run ``find_by_shared_topics`` (S1) +
             ``find_by_stargazer_overlap`` (S2), merge candidates keyed by
             lowercased ``owner/repo``, tally which seeds surfaced each.
          4. README lens (skipped when ``mode == 'off'``): fetch the seeds' READMEs
             and the top candidates' READMEs, attach a ``readme_similarity`` per
             candidate. A 403/429 aborts the README lens for the rest of the scan.
          5. ``rank_candidates`` over the merged dicts (renormalized PER-CANDIDATE
             over its present signals); gate on ``MIN_SCORE`` + ``TOP_N`` and
             ``upsert_suggestion`` each candidate NOT already watched.
          6. ``{scanned, suggestions, readme_mode, seeds_total, seeds_scanned,
             truncated}``.

        ``truncated`` is True when the seed cap or request budget stopped the scan
        short of every parsed seed; ``seeds_scanned`` vs ``seeds_total`` quantify
        it. Idempotent: the DAO UPSERTs on ``(project, owner, repo)`` and keeps a
        dismissed/added verdict sticky, so a re-scan refreshes scores without
        duplicating or resurrecting. Degrades gracefully with NO PAT (the client
        short-circuits to ``[]`` → 0 candidates → 0 rows, no raise).
        """
        mode = cls._resolve_readme_mode(readme_mode)

        seeds = [
            s
            for s in CompetitorSourceService.list_sources(project_id)
            if s.get("kind") == "github_repo"
        ]
        if not seeds:
            return {
                "scanned": 0,
                "suggestions": 0,
                "readme_mode": mode,
                "seeds_total": 0,
                "seeds_scanned": 0,
                "truncated": False,
            }

        # (owner_lc, repo_lc) the project already watches — excluded from output.
        existing_watched: set[tuple[str, str]] = set()
        parsed_seeds: list[tuple[str, str]] = []
        for seed in seeds:
            try:
                owner, repo = GitHubSimilarityClient.parse_seed(seed.get("url") or "")
            except ValueError:
                # A non owner/repo seed URL is skipped (never aborts the scan).
                logger.warning("discovery: unparseable seed url %r — skipping", seed.get("url"))
                continue
            existing_watched.add((owner.lower(), repo.lower()))
            parsed_seeds.append((owner, repo))

        seeds_total = len(parsed_seeds)
        seed_cap = max(0, max_seeds)
        request_budget = max(1, max_requests)

        # Merge candidates across seeds keyed by lowercased owner/repo. Enforce
        # the seed cap and a scan-wide request-budget circuit-breaker: stop
        # launching further seed fan-outs once the running estimate would blow
        # the budget. ``truncated`` records that we stopped short of every seed.
        merged: dict[tuple[str, str], dict] = {}
        seed_meta_by_key: dict[tuple[str, str], dict] = {}
        seeds_scanned = 0
        est_requests = 0
        truncated = seeds_total > seed_cap
        for owner, repo in parsed_seeds[:seed_cap]:
            if est_requests + _EST_REQUESTS_PER_SEED > request_budget:
                truncated = True
                logger.warning(
                    "discovery: scan-wide request budget (%d) reached after %d seeds — truncating",
                    request_budget,
                    seeds_scanned,
                )
                break
            est_requests += _EST_REQUESTS_PER_SEED
            seeds_scanned += 1
            try:
                cls._scan_one_seed(owner, repo, merged, seed_meta_by_key)
            except Exception:  # noqa: BLE001 — one failing seed never aborts the scan
                logger.warning("discovery: seed %s/%s scan failed — skipping", owner, repo)
                continue

        # Drop forks / archived / already-watched candidates before ranking.
        candidates: list[dict] = []
        for key, cand in merged.items():
            if key in existing_watched:
                continue
            if cand.get("fork") or cand.get("archived"):
                continue
            candidates.append(cand)

        # README lens — best-effort, only the top candidates, never blocks.
        active_signals = {"star", "topic", "prior"}
        if mode != README_MODE_OFF and candidates:
            cls._attach_readme_similarity(candidates, seed_meta_by_key, mode, active_signals)

        # Multi-seed candidates (surfaced by >= 2 seeds) get the prior bonus.
        multi_seed_keys = {
            (c["owner"].lower(), c["repo"].lower())
            for c in candidates
            if len(c.get("seed_hits") or []) >= 2
        }
        # Use the first seed's metadata for same_language (best-effort; the prior
        # signal is the lowest-weight and only nudges ordering).
        seed_meta = next(iter(seed_meta_by_key.values()), None)

        ranked = discovery_ranker.rank_candidates(
            seed_meta,
            candidates,
            active_signals=active_signals,
            multi_seed_keys=multi_seed_keys,
        )

        written = 0
        for cand in ranked[: discovery_ranker.TOP_N]:
            if cand["score"] < discovery_ranker.MIN_SCORE:
                continue
            key = (cand["owner"].lower(), cand["repo"].lower())
            if key in existing_watched:
                continue
            discovery_suggestions.upsert_suggestion(
                project_id,
                cand["owner"],
                cand["repo"],
                cand["url"],
                score=cand["score"],
                reason=cand["reason"],
                evidence=cand["evidence"],
            )
            written += 1

        return {
            "scanned": seeds_scanned,
            "suggestions": written,
            "readme_mode": mode,
            "seeds_total": seeds_total,
            "seeds_scanned": seeds_scanned,
            "truncated": truncated,
        }

    @staticmethod
    def _scan_one_seed(
        owner: str,
        repo: str,
        merged: dict[tuple[str, str], dict],
        seed_meta_by_key: dict[tuple[str, str], dict],
    ) -> None:
        """Run S1 + S2 for one seed and fold the candidates into ``merged``.

        Records the seed's own metadata (for ``same_language``) and tags each
        candidate with the seed that surfaced it (``seed_hits``) for the
        ``multi_seed_bonus`` tally. Both client calls short-circuit to ``[]`` with
        no PAT / on throttle, so this is a safe no-op in that case.
        """
        seed_key = (owner.lower(), repo.lower())
        meta = GitHubSimilarityClient.repo_metadata(owner, repo)
        if meta is not None:
            seed_meta_by_key[seed_key] = meta

        topic_hits = GitHubSimilarityClient.find_by_shared_topics(owner, repo)
        star_hits = GitHubSimilarityClient.find_by_stargazer_overlap(owner, repo)

        seed_label = f"{owner}/{repo}"
        for cand in list(topic_hits) + list(star_hits):
            c_owner = cand.get("owner") or ""
            c_repo = cand.get("repo") or ""
            if not c_owner or not c_repo:
                continue
            key = (c_owner.lower(), c_repo.lower())
            if key == seed_key:
                continue  # never suggest the seed itself
            bucket = merged.get(key)
            if bucket is None:
                bucket = {"owner": c_owner, "repo": c_repo, "seed_hits": []}
                merged[key] = bucket
            # Merge signal fields, preferring the first non-empty value seen.
            for field in (
                "url",
                "stargazers_count",
                "language",
                "topics",
                "shared_topics",
                "shared_stargazers",
                "shared_stargazer_logins",
                "archived",
                "fork",
            ):
                if field in cand and (bucket.get(field) in (None, [], 0) or field not in bucket):
                    bucket[field] = cand[field]
            if seed_label not in bucket["seed_hits"]:
                bucket["seed_hits"].append(seed_label)

    @classmethod
    def _attach_readme_similarity(
        cls,
        candidates: list[dict],
        seed_meta_by_key: dict[tuple[str, str], dict],
        mode: str,
        active_signals: set[str],
    ) -> None:
        """Attach a ``readme_similarity`` to the top candidates (best-effort).

        Fetches one representative seed README (the first seed) and each top
        candidate's README, computes the similarity under ``mode`` and folds it
        onto the candidate dict. When at least one candidate gets a non-null
        similarity, ``'readme'`` is added to ``active_signals`` so the ranker may
        weight it (per-candidate); candidates without a README keep it absent (no
        penalty). On a 403/429 throttle (the ``_README_THROTTLED`` sentinel out of
        :meth:`_fetch_readme`) the WHOLE lens aborts — we stop fetching further
        READMEs and back off rather than burning the rest of the scan's budget on
        guaranteed-throttled GETs. Strictly best-effort — any failure leaves
        README simply unset.
        """
        # One representative seed README is enough to gauge candidate overlap; the
        # seed set is the project's own watched competitors (all on-topic).
        seed_owner_repo = next(iter(seed_meta_by_key.keys()), None)
        if seed_owner_repo is None:
            return
        seed_meta = seed_meta_by_key[seed_owner_repo]
        seed_readme = cls._fetch_readme(seed_meta["owner"], seed_meta["repo"])
        # A throttle on the seed README aborts the lens before any candidate fetch.
        if seed_readme is _README_THROTTLED or not seed_readme:
            return

        fired = False
        for cand in candidates[:_README_CANDIDATE_CAP]:
            cand_readme = cls._fetch_readme(cand["owner"], cand["repo"])
            if cand_readme is _README_THROTTLED:
                # Throttled mid-lens: stop the whole README fan-out and back off.
                break
            if not cand_readme:
                continue
            sim = cls._readme_similarity(seed_readme, cand_readme, mode)
            if sim is not None:
                cand["readme_similarity"] = sim
                fired = True
        if fired:
            active_signals.add("readme")

    # -- read -----------------------------------------------------------------

    @staticmethod
    def list_suggestions(project_id: str, *, statuses: Optional[list] = None) -> list[dict]:
        """Project-scoped suggestion queue — delegates to the 24-01 DAO.

        ``statuses`` filters by status (e.g. ``['suggested']`` for the active
        queue); default returns all. Highest-scored first (NULLs last).
        """
        return discovery_suggestions.list_suggestions(project_id, statuses=statuses)

    # -- promote / dismiss ----------------------------------------------------

    @staticmethod
    def promote_suggestion(project_id: str, suggestion_id: str) -> dict:
        """Promote a suggestion into a watched ``competitor_source`` (the P1 hook).

        Project-SCOPED (the IDOR fix): the suggestion is looked up under
        ``project_id`` and a foreign-project id raises ``ValueError`` (the route
        404s) — a caller authorized for project A cannot promote a suggestion
        owned by project B by pairing A's URL with B's id.

        IDEMPOTENT on the suggestion's current status:

          * ``'suggested'`` → calls
            ``add_source(project_id, url, origin='discovery')`` (the discovery
            hook — NO signature change) and stamps ``set_status('added',
            source_id=<new id>)``; returns the NEW source.
          * ``'added'`` → already promoted: returns the EXISTING
            ``competitor_source`` (by the stamped ``source_id``) WITHOUT calling
            ``add_source`` again, so a double-accept never duplicates rows.
          * ``'dismissed'`` → raises ``PromotionConflict`` (the route maps it to a
            409): a dismissed candidate must be re-suggested before it can be
            promoted, not silently resurrected.

        Returns ``{"source": <source row>, "suggestion": <row>}``. Raises
        ``ValueError`` on an unknown / foreign-project ``suggestion_id``.

        Concurrency-safe: the ``suggested`` → ``added`` flip is an ATOMIC
        conditional UPDATE (``claim_for_promotion``), so two concurrent accepts
        cannot both pass the status check and both call ``add_source`` — only the
        single claim winner adds the source (``competitor_source`` carries no
        ``UNIQUE(project_id, url)``, so a double-add would otherwise duplicate the
        row). The loser re-reads and returns the existing source.
        """
        # Project-scoped read up front: a foreign-project / unknown id is a 404
        # (and gives us the immutable candidate_url for the add).
        suggestion = discovery_suggestions.get_suggestion(suggestion_id, project_id=project_id)
        if suggestion is None:
            raise ValueError(f"Unknown discovery suggestion: {suggestion_id}")

        # Atomic claim: only one concurrent caller flips 'suggested'→'added'.
        if discovery_suggestions.claim_for_promotion(suggestion_id, project_id):
            try:
                source = CompetitorSourceService.add_source(
                    project_id,
                    suggestion["candidate_url"],
                    origin="discovery",
                )
            except Exception:
                # The add failed AFTER we claimed — revert so we never leave a
                # phantom 'added' row with no backing competitor_source.
                discovery_suggestions.revert_promotion_claim(suggestion_id, project_id)
                raise
            # Stamp the new source id onto the (already 'added') row.
            updated = discovery_suggestions.set_status(
                suggestion_id, "added", project_id=project_id, source_id=source["id"]
            )
            return {"source": source, "suggestion": updated}

        # We did NOT win the claim. Re-read the (project-scoped) row and resolve.
        suggestion = discovery_suggestions.get_suggestion(suggestion_id, project_id=project_id)
        if suggestion is None:
            # Raced into deletion between the two reads — treat as not-found.
            raise ValueError(f"Unknown discovery suggestion: {suggestion_id}")

        status = suggestion.get("status")
        if status == "added":
            # Already promoted (by us earlier, or a concurrent winner) — return the
            # existing source, do NOT add a second one.
            source_id = suggestion.get("source_id")
            source = CompetitorSourceService.get_source(source_id) if source_id else None
            return {"source": source, "suggestion": suggestion}
        if status == "dismissed":
            raise PromotionConflict(
                f"Suggestion {suggestion_id} was dismissed; re-suggest before promoting"
            )
        # Claim failed but the row is neither 'added' nor 'dismissed' → it does not
        # exist under this project (foreign-project / unknown id) → not-found.
        raise ValueError(f"Unknown discovery suggestion: {suggestion_id}")

    @staticmethod
    def dismiss_suggestion(project_id: str, suggestion_id: str) -> dict:
        """Dismiss a suggestion — ``set_status(id, 'dismissed')`` (sticky on re-scan).

        Project-SCOPED (the IDOR fix): the suggestion is looked up and mutated
        under ``project_id``; a foreign-project id raises ``ValueError`` (the route
        404s). Returns ``{"suggestion": <updated row>}``.
        """
        suggestion = discovery_suggestions.get_suggestion(suggestion_id, project_id=project_id)
        if suggestion is None:
            raise ValueError(f"Unknown discovery suggestion: {suggestion_id}")
        updated = discovery_suggestions.set_status(
            suggestion_id, "dismissed", project_id=project_id
        )
        return {"suggestion": updated}
