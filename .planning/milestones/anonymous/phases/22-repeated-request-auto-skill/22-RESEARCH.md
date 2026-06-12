# Phase 22: Repeated-request Auto-skill - Research

**Researched:** 2026-06-13
**Domain:** Backend Python — self-improvement loop (signal store, embedding match, safety gate, forge skill creation)
**Confidence:** HIGH (every recommendation grounded in real codebase symbols/line numbers; no external papers apply)

## Summary

Phase 22 is backend-only and **codebase-grounded** — there is no academic baseline. The
infrastructure it needs already exists and is well-factored: a session-completion event bus
(`execution_events`), a per-session-kind text fetcher map (`_FETCHERS`), an embedding service
with a cosine helper, a takeaway store with auto-apply, a Forge skill-create dispatch that
already writes `SKILL.md`, and an origin-hash provenance table. The phase's job is to add ONE
new store (`repeated_request_signals`), ONE new detection handler registered on the existing
bus, ONE safety scanner, and ONE hybrid gate — then wire them together and fix two
consistency gaps (REQ-26).

**Primary recommendation:** Mirror the existing `harness_failure_annotator` /
`harness_takeaway_extractor` pattern exactly. Register the new detector as an additional
`register_session_handler(...)` callback (do NOT edit `on_session_complete`); reuse
`_FETCHERS` for user-turn text; reuse `embedding_service.embed_text` + `cosine_similarity`;
reuse the evolver's `_create_dispatch["skill"]` (already-working SKILL.md writer) for the
AUTO path; reuse `forge_origin.record_origin`/`get_origin` for provenance.

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase. The binding spec is `22-EVAL.md` (already written) plus
REQ-22…REQ-26. Treat the EVAL.md module layout as the **intended target**, with the
corrections below where it diverges from real conventions.

## Architecture Patterns (grounded in real files)

### The session-completion bus (REQ-23 anchor)

- `app/services/execution_events.py`
  - `register_session_handler(callback: SessionCallback)` — line 38. Callback signature:
    `(session_kind, session_id, project_id, status, output) -> None`.
  - `emit_session_complete(session_kind, session_id, project_id, status, output)` — line 48.
    Iterates handlers, **catches per-handler exceptions** (line 60-65) so one handler cannot
    block others.
  - `clear_session_handlers()` — line 70 (test helper).
- **All 5 kinds already emit** `emit_session_complete`:
  - `execution_service.py:1006` (trigger_execution)
  - `super_agent_session_service.py:335` (super_agent)
  - `team_execution_service.py:238` (team_session)
  - `project_session_manager.py:1395` (project_session) — and workflow path.
- **Registration pattern to mirror** — `harness_failure_annotator.py:14-16`:
  ```python
  from app.services.execution_events import register_session_handler
  from app.services.harness_failure_annotator import on_session_complete
  register_session_handler(on_session_complete)
  ```
  This block runs at import/startup. The takeaway extractor registers the same way. **The new
  detector registers a THIRD handler** — it does not modify the existing two.

**CRITICAL correction to EVAL.md P4:** EVAL.md P4 says "detector exception does not escape
`on_session_complete`". That is mis-scoped — the new detector is its OWN handler, not a call
inside the takeaway extractor's `on_session_complete`. Non-blocking is already guaranteed by
`emit_session_complete`'s per-handler try/except (line 60). The P4 test should monkeypatch
`detect_for_session` to raise and assert `emit_session_complete(...)` still returns and OTHER
handlers still run. The planner should re-target P4 accordingly.

### Per-session-kind user-turn extraction (REQ-23)

- `app/services/harness_failure_annotator.py:304` —
  ```python
  _FETCHERS: dict[str, SessionFetcher] = {
      "trigger_execution": _fetch_trigger_execution,
      "super_agent": _fetch_super_agent_session,
      "project_session": _fetch_project_session,
      "workflow": _fetch_workflow,
      "team_session": _fetch_team_session,
  }
  ```
  Each fetcher returns `Optional[SessionPayload]`. `SessionFetcher = Callable[[str], Optional[SessionPayload]]`.
- The detector should import `_FETCHERS` (the takeaway extractor already does — line 43) and
  call `fetcher(session_id)` to get the session text, then extract user-turn text from the
  payload. Reuse `extract_for_session`'s guard idiom (`fetcher = _FETCHERS.get(session_kind);
  if fetcher is None: return []`, `harness_takeaway_extractor.py:1064`).

### Embedding + cosine match (REQ-23, threshold 0.83)

- `app/services/embedding_service.py`:
  - `embed_text(text) -> list[float] | None` — line 54. Returns `None` when
    `sentence-transformers` is unavailable (the documented embed-disabled fallback path; EVAL
    A1). Model `all-MiniLM-L6-v2`, **dim 384**, vectors **pre-normalized**.
  - `cosine_similarity(a, b) -> float` — line 71. For normalized vectors = dot product.
  - `cosine_similarity_batch(query, candidates) -> list[float]` — line 77 (use this to match a
    new request against all existing signal embeddings in one call).
  - `serialize_embedding(emb) -> bytes` (line 60) / `deserialize_embedding(blob)` (line 65) —
    use these to store the embedding as a BLOB column on the signal row (matches how
    `agent_memory` stores embeddings).
- **The 0.83 threshold does NOT exist anywhere in the codebase** — it is introduced by this
  phase. Define it as a module constant (e.g. `_COSINE_MATCH_THRESHOLD = 0.83`) in the
  detector. Cite it in code comments as a Phase-22 design constant, not an existing value.
- **Embed-disabled fallback (A1):** when `embed_text` returns `None`, fall back to exact
  normalized-request-hash match (`normalize_request_hash`). No crash; verbatim repeats still
  coalesce; paraphrases stay separate.

### Verification-record awareness (REQ-22 `verified_success_count`)

- `app/db/schema/_verification_records.py` — `verification_records(execution_id, claim,
  status CHECK IN ('pending','passed','failed'), ...)`, FK to `execution_logs(execution_id)`.
- `app/db/verification_records.py` is the repo. Source `verified_success_count` by counting
  `status='passed'` records for the executions tied to a signal's `example_session_ids` (for
  `trigger_execution` kind, session_id == execution_id). For non-execution kinds verification
  records may not exist — treat absent as 0 verified (gate then routes to PROPOSE).

### Forge skill creation + provenance (REQ-24 AUTO path, REQ-25)

- **Skill creation already works** (Phase 17). Two viable paths — the planner must pick one
  and be consistent:
  1. **Evolver dispatch (recommended, simplest):** `harness_evolver._create_dispatch["skill"]`
     — proven by `tests/test_forge_skill_dispatch.py`:
     `ev._create_dispatch["skill"](name=..., payload={"description":..., "content":...},
     project_id=...)` writes `.claude/skills/<name>/SKILL.md` AND a `user_skills` row, returns
     `asset_id`. `WRITABLE_KINDS` (harness_evolver.py:67) already includes `"skill"`.
  2. **`create_and_bind_and_materialize`** — `app/services/forge_create_service.py:73`,
     signature `(project_id, kind, payload, bind=True, materialize=True) -> dict`. Atomic via
     LIFO compensation. `kind` must be in `VALID_FORGE_BINDING_KINDS` (= `app/db.VALID_KINDS`,
     aliased at `app/db/__init__.py:557`) and in `_CREATE_FNS` (forge_create_service.py:48).
     **VERIFY `"skill"` is in both before relying on this path** — the evolver uses its own
     `_create_dispatch`, which suggests skill-create may live there, not in `_CREATE_FNS`. The
     EVAL.md names `create_and_bind_and_materialize`; the planner must confirm skill support
     there or switch the AUTO path to the evolver dispatch.
- **Provenance:** `app/db/forge_origin.py` — `record_origin(asset_id, kind, origin_hash,
  source_session_id)` (UPSERT) and `get_origin(asset_id, kind) -> Optional[dict]`.
  `origin_hash` is a sha256 of the source-file content. `provenance_allows_overwrite` (new)
  re-hashes the on-disk SKILL.md and compares to stored `origin_hash`; if they diverge, the
  operator modified the skill → refuse overwrite. Mirror the idempotence pattern in
  `forge_session_import.py:130-185` (get_origin check → write → record_origin).
- **Dedup index:** bound skills are in `user_skills` (`app/db/schema/_skills.py`:
  `skill_name UNIQUE`) and `project_skills` (`UNIQUE(project_id, skill_name)`). Use
  `skills_repo.get_user_skill_by_name(name)` (proven in the dispatch test) +
  name-cosine for near-duplicate detection → patch-over-create.

### Hybrid gate + takeaway auto-apply (REQ-24)

- `discovered_procedure` is a valid takeaway kind — `app/db/schema/_harness_takeaways.py`
  CHECK constraint and `app/db/harness_takeaways.py:12 VALID_KINDS`. `insert_many(takeaways)`
  at line 27 validates kind. Confidence stored as `confidence REAL DEFAULT 0.5`.
- **Current auto-apply gate is an env flag** — `harness_takeaway_extractor.py:1032`:
  ```python
  def _autoapply_enabled() -> bool:
      return os.environ.get("AGENTED_TAKEAWAY_AUTOAPPLY", "0") == "1"
  ```
  (Note: the flag is `AGENTED_TAKEAWAY_AUTOAPPLY`, not `AGENTED_AUTONOMY` as the targets
  hint suggests — verify both; `AGENTED_AUTONOMY` may gate a different layer.)
- **Per-project policy already exists** — `app/db/schema/_project_autonomy.py`:
  `project_autonomy_config(project_id PK, enabled INTEGER, policy_json TEXT, updated_at)`.
  **REQ-24's "promote env flag to per-project policy" means:** read
  `project_autonomy_config` for the signal's project; fall back to the env flag only when no
  row. The gate's AUTO branch consults this policy.

### Consistency fixes (REQ-26)

1. **`tesserae_integration._build_harness_session` gap** — `tesserae_integration.py:375-422`.
   The `else` branch (line 418) explicitly returns `None` for `project_session`, `workflow`,
   `team_session` ("not normalized yet… Skip"). REQ-26 requires normalizers for these three,
   mirroring `_normalize_super_agent_session` (line 273) and `_normalize_trigger_execution`
   (line 313). Each needs a `SELECT * FROM <table> WHERE id = ?` + a normalizer returning the
   HarnessSession fields (`title`/`agent_label`/`messages`/etc.). EVAL S5
   (`test_build_harness_session_kinds.py`) asserts all five kinds return a normalized record.
2. **Evolver `_DESIGN_GUIDE` / `_PROMPT_TEMPLATE`** — `harness_evolver.py:308` / `:383`. They
   currently describe skills as **read-only/deferred** (lines 16-18, 65-66, 328, 339, 391:
   "Skills create/update is deferred", "skills/<name>.json (read-only — do not edit)").
   But `WRITABLE_KINDS` (line 67) and `_create_dispatch["skill"]` already make skills
   writable. REQ-26 "reflect writable skills" = update these two prompt strings so the LLM
   knows it MAY now create/update skills. This is a text edit, no logic change.

## Recommended File Layout (EVAL.md target, corrected)

| EVAL.md path | Verdict | Note |
|---|---|---|
| `app/db/schema/_repeated_request_signals.py` | CREATE | Mirror `_project_autonomy.py`/`_harness_takeaways.py`. Register in `schema/__init__.py` import block AND in `create_fresh_schema` body (after `create_harness_takeaway_tables`). 1 table + 3 indexes per EVAL S3. |
| `app/db/repeated_request_signals.py` | CREATE | Raw-SQLite repo. `upsert_signal`, `list_signals`, `get_signal`, `mark_skill_created`, `normalize_request_hash`. Use `app.db.connection.get_connection()` ctx manager (per `_build_harness_session`). UPSERT via `ON CONFLICT(request_hash) DO UPDATE` preserving `first_seen_at`, incrementing `occurrence_count`, FIFO-capping `example_session_ids` at 5. |
| `app/models/repeated_request_signal.py` | CREATE | Pydantic v2 model (mirror existing `app/models/`). |
| `app/services/repeated_request_detector.py` | CREATE | `detect_for_session(session_kind, session_id, project_id)`. Imports `_FETCHERS`, `embed_text`, `cosine_similarity_batch`, the signal repo. Registers via `register_session_handler` at module import (mirror annotator). |
| `app/services/skill_safety_scanner.py` | CREATE | `scan_skill_content`, `find_duplicate_binding`, `provenance_allows_overwrite`. Pure-ish; uses `forge_origin`, `skills` repo. |
| `app/services/repeated_request_gate.py` | CREATE | `evaluate_signal`, `convert_signal`, `GateDecision`. Pure function over (occurrence_count, verified_success_count, scan, dedup, provenance, policy). |
| tests (7 files) + `tests/fixtures/repeated_request_transcripts.py` | CREATE | Use `isolated_db` (autouse, conftest.py:52 — calls `init_db()` which runs migrations + fresh schema). |

**forge_origin schema gap (IMPORTANT):** `forge_origin` is created ONLY by migration
`_migrate_157_forge_origin` (`app/db/migrations/v07_features.py:1131`), NOT by
`create_fresh_schema`. `init_db()` runs migrations, so `isolated_db` tests get the table.
But the EVAL S3 raw `create_fresh_schema(:memory:)` smoke test will NOT have `forge_origin`.
The planner should: (a) keep provenance tests on the `isolated_db`/`init_db()` path, and
(b) consider adding `forge_origin` to a fresh-schema module as a defensive REQ-25 sub-task.

## Wave / Dependency Structure (6 components)

```
Wave 1 (no deps, parallel):
  22-01  signal store      (_repeated_request_signals.py + repeated_request_signals.py + model + test)
  22-02  consistency fixes (_build_harness_session normalizers + evolver prompt strings + 2 tests)  [INDEPENDENT]
  22-04a safety scanner    (skill_safety_scanner.py + test) — pure, depends only on forge_origin/skills repos (exist)

Wave 2 (depends on Wave 1):
  22-03  detector          (needs signal store from 22-01; reuses _FETCHERS/embed_text)
  22-04b dedup/provenance  (needs scanner from 22-04a + forge_origin)

Wave 3 (depends on Wave 2):
  22-05  hybrid gate       (needs detector signals + scanner + dedup + project_autonomy + skill-create path)

Wave 4 (deferred, manual):
  22-06  live dogfood (D1/D2) — real transcripts, operator review
```

22-02 is fully independent and can land first/anytime. The signal store (22-01) gates the
detector and gate. The gate (22-05) is the integration point that ties all pieces + the
skill-create path together.

## Don't Hand-Roll

| Problem | Use Instead | Location |
|---|---|---|
| Session text per kind | `_FETCHERS` | `harness_failure_annotator.py:304` |
| Embedding + cosine | `embed_text`, `cosine_similarity_batch` | `embedding_service.py:54,77` |
| Embedding BLOB (de)serialization | `serialize_embedding`/`deserialize_embedding` | `embedding_service.py:60,65` |
| Skill file+row creation | `_create_dispatch["skill"]` | `harness_evolver.py` (test_forge_skill_dispatch.py) |
| Provenance hash store | `record_origin`/`get_origin` | `app/db/forge_origin.py` |
| Per-project autonomy policy | `project_autonomy_config` | `app/db/schema/_project_autonomy.py` |
| Non-blocking handler dispatch | `emit_session_complete` try/except | `execution_events.py:60` |
| DB connection | `get_connection()` ctx manager | `app.db.connection` |

## Common Pitfalls

1. **Editing `on_session_complete` instead of registering a new handler.** Register a third
   `register_session_handler` callback. Editing the takeaway extractor couples concerns and
   breaks the "best-effort, isolated handlers" contract.
2. **Assuming `create_and_bind_and_materialize` supports `"skill"`.** The evolver uses its own
   `_create_dispatch`. Verify `"skill" in _CREATE_FNS` before using the forge path; otherwise
   use the evolver dispatch.
3. **`forge_origin` absent on bare `create_fresh_schema`.** It's migration-only (#157). Tests
   must go through `init_db()` (the `isolated_db` fixture does).
4. **0.83 is a new constant, not an existing value.** Don't grep for it and assume it's wired —
   define it.
5. **`AGENTED_TAKEAWAY_AUTOAPPLY` vs `AGENTED_AUTONOMY`.** The takeaway auto-apply flag is
   `AGENTED_TAKEAWAY_AUTOAPPLY` (extractor:1032). Confirm which flag REQ-24 means to promote.
6. **Invisible-Unicode scan must cover zero-width + bidi + tag chars** (U+200B-200F, U+202A-202E,
   U+2060-2064, U+E0000-E007F). Fail-closed: any match → unsafe.

## Verification Strategy

| Item | Tier | Rationale |
|---|---|---|
| Ruff/import/DDL smoke (S1-S3) | L1 Sanity | Immediate |
| Signal store UPSERT invariants (S4) | L1 | `isolated_db` unit |
| `_build_harness_session` 5-kind (S5) | L1 | Unit on normalizers |
| Safety scanner reject known payloads (S6) | L1 | Pure unit, fail-closed |
| Cosine precision on fixtures (P1) | L2 Proxy | Same embedding backend as prod |
| Gate matrix (P2) | L2 | Pure function, mock skill-create |
| Dedup/provenance (P3) | L2 | Seeded `isolated_db` |
| Non-blocking (P4, re-scoped) | L2 | Assert via `emit_session_complete`, not extractor |
| Live dogfood (D1), operator review (D2) | L3 Deferred | Real transcripts, human judgment |

## Open Questions

1. **Which skill-create path** — `_create_dispatch["skill"]` (proven) vs
   `create_and_bind_and_materialize` (EVAL-named, skill support unverified). Recommend the
   evolver dispatch unless the planner confirms `"skill" in _CREATE_FNS`.
2. **Which autonomy flag** REQ-24 promotes — `AGENTED_TAKEAWAY_AUTOAPPLY` (most likely) vs
   `AGENTED_AUTONOMY`. Verify before writing the gate's policy lookup.
3. **`forge_origin` fresh-schema** — add to `create_fresh_schema` (defensive) or leave
   migration-only and route all tests through `init_db()`? Recommend the latter for minimal
   scope, with a note.
4. **Verification-record sourcing for non-trigger kinds** — `verification_records` is keyed by
   `execution_id`. For `project_session`/`workflow`/`team_session`/`super_agent`, confirm
   whether any verification records exist; if not, those kinds always count 0 verified →
   PROPOSE-only. Acceptable per EVAL but should be explicit in the gate.

## Sources

### Primary (HIGH — real codebase, this worktree)
- `app/services/execution_events.py` (bus: register/emit, lines 38/48/60/70)
- `app/services/harness_failure_annotator.py` (`_FETCHERS` :304, registration :14-16)
- `app/services/harness_takeaway_extractor.py` (`on_session_complete` :1121, `_autoapply_enabled` :1032, `extract_for_session` :1055)
- `app/services/embedding_service.py` (`embed_text` :54, `cosine_similarity` :71, batch :77, dim 384)
- `app/services/forge_create_service.py` (`create_and_bind_and_materialize` :73, `_CREATE_FNS` :48)
- `app/services/harness_evolver.py` (`WRITABLE_KINDS` :67, `_DESIGN_GUIDE` :308, `_PROMPT_TEMPLATE` :383, `_create_dispatch["skill"]`)
- `app/services/tesserae_integration.py` (`_build_harness_session` :375, normalizers :273/:313, gap `else` :418)
- `app/db/forge_origin.py` (`record_origin` :27, `get_origin` :51)
- `app/db/schema/__init__.py` (`create_fresh_schema` :41, import block :11-36)
- `app/db/schema/_harness_takeaways.py`, `_project_autonomy.py`, `_verification_records.py`, `_skills.py` (DDL patterns to mirror)
- `app/db/harness_takeaways.py` (`VALID_KINDS` :12, `insert_many` :27)
- `app/db/migrations/v07_features.py:1131` (`_migrate_157_forge_origin`)
- `tests/conftest.py:52` (`isolated_db` → `init_db()`)
- `tests/test_forge_skill_dispatch.py` (proven skill-create dispatch usage)

## Metadata

**Confidence breakdown:**
- Stack/symbols: HIGH — read real files, cited line numbers.
- Architecture/wave structure: HIGH — derived from existing handler-registration pattern.
- Skill-create path choice: MEDIUM — two viable paths; planner must pick after a 1-line verify.
- Autonomy flag identity: MEDIUM — `AGENTED_TAKEAWAY_AUTOAPPLY` confirmed; REQ wording ambiguous.

**Research date:** 2026-06-13
**Valid until:** ~30 days (stable backend; no fast-moving external deps)

## RESEARCH COMPLETE

**Phase:** 22 - Repeated-request Auto-skill
**Confidence:** HIGH

### Key Findings
- The self-improvement loop's substrate already exists: `execution_events` bus (all 5 kinds
  emit), `_FETCHERS` text map, `embedding_service` (cosine, dim 384), `project_autonomy_config`
  per-project policy, evolver `_create_dispatch["skill"]` (already writes SKILL.md), and
  `forge_origin` provenance. The phase is mostly assembly + 2 consistency edits.
- The detector must register as a NEW `register_session_handler` callback (mirror
  `harness_failure_annotator.py:14-16`) — NOT edit `on_session_complete`. Non-blocking is
  already guaranteed by `emit_session_complete`'s per-handler try/except — EVAL P4 should be
  re-scoped accordingly.
- The 0.83 cosine threshold is NEW (not in code); `embed_text` returns `None` when
  sentence-transformers is absent (the A1 fallback path → exact-hash match).
- `forge_origin` is migration-only (#157), absent from `create_fresh_schema` — provenance
  tests must run through `init_db()` (the `isolated_db` fixture does).
- Skill auto-creation already works via the evolver dispatch; `create_and_bind_and_materialize`
  skill support is UNVERIFIED — planner picks the path after a 1-line check.

### Verification Strategy
- L1 Sanity: 7 (ruff, import, DDL, store, 5-kind normalize, scanner, build)
- L2 Proxy: 4 (cosine precision, gate matrix, dedup/provenance, non-blocking [re-scoped])
- L3 Deferred: 2 (live dogfood, operator review)

### Open Questions
Skill-create path choice; autonomy-flag identity; forge_origin fresh-schema decision;
verification-record sourcing for non-trigger kinds. All low-risk, resolvable at plan time.

### File Created
`.planning/milestones/anonymous/phases/22-repeated-request-auto-skill/22-RESEARCH.md`

### Ready for Planning
Research complete. Planner can create PLAN.md files with concrete symbols and line-numbered
call targets.
