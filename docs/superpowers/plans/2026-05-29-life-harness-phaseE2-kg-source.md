# Phase E2 — Tesserae KG as a first-class evolution input

**Branch:** `feat/life-harness-phaseE2-kg-source` (off `main` @ 44b4723c)
**Goal:** Close the self-improvement loop's final edge — the compiled
Tesserae knowledge graph feeds **structured, weighted, deduped signal**
into `gather_inputs`, so evolution rounds are seeded by what the KG
*discovers* (recurring un-codified patterns / decisions / failure modes),
not only by raw trajectories + takeaways.

## Re-baseline (verified against source 2026-05-31)

- `gather_inputs` (`harness_evolver.py:381`) returns
  `{project_id, primitives, trajectories, takeaways}` — **no KG signal.**
- Tesserae is used today only by `_build_tesserae_context_md`
  (`harness_evolver.py:651`): it asks `ask_tesserae` **one question per
  takeaway** and writes prose `tesserae_context.md`. That is
  *takeaway-derived Q&A enrichment* — NOT KG-native discovery and NOT a
  structured, persisted, deduped, weighted input. E2 adds the latter and
  leaves `_build_tesserae_context_md` untouched (complementary).
- The **only** Python Tesserae query helper is
  `ask_tesserae(project_id, question, *, top_k=5) -> Optional[str]`
  (`tesserae_integration.py:948`, a `tesserae ask` CLI shell-out returning
  markdown or None). There is **no** Python binding for
  fresh_insights/communities/search_facts — E2 MUST derive signal via a
  small bounded set of `ask_tesserae` discovery questions, NOT by shelling
  out to CLI subcommands that may not exist in the installed `tesserae`.
- Gating helper: `get_tesserae_root(project_id) -> Optional[Path]`
  (`tesserae_integration.py:75`); `None` ⇒ Tesserae not enabled.
- Round-column pattern: `_harness_evolution.py` CREATE TABLE +
  `_ROUND_COLUMNS_IN_ORDER` tuple (`harness_evolution.py:53`) + nested
  `_ensure_*_columns(conn)` runtime PRAGMA-guarded ALTER chain
  (`:80/:97/:119/:127`). `start_round` (`harness_evolution.py:8`) takes
  `input_forge: dict` and JSON-dumps it into the INSERT (`:25`).
  Call site: `harness_evolver.py:1432` (created AFTER `gather_inputs`).

## Design decisions (locked — do not re-litigate)

1. **Discovery questions, not takeaway echo.** A small fixed tuple
   `_DISCOVERY_QUESTIONS` (≤ 3) asks the KG for *un-codified* recurring
   structure, e.g.:
   - "What recurring problems, mistakes, or decisions appear across this
     project's past sessions that are NOT yet codified as a rule, hook, or
     command? List each as one concise actionable item."
   - "What domain conventions or procedures recur across the project's
     code and docs that a reusable skill should capture?"
   - "What single most impactful guardrail is missing given recent
     session failures?"
   Cap at 3 ⇒ ≤ 3 `ask_tesserae` calls/round (bounded LLM cost).
2. **Weight band [0.3, 0.7], 30-day half-life, fresh-rewards-new decay.**
   A signal's weight decays by the age of its FIRST sighting:
   `w = clamp(W_MAX * 2**(-age_days / HALF_LIFE_DAYS), W_MIN, W_MAX)`
   with `W_MAX=0.7, W_MIN=0.3, HALF_LIFE_DAYS=30`. New signal ⇒ 0.7;
   a signal still surfacing 30d after first sighting ⇒ ~0.35 → floor.
   This down-weights stale KG signal that keeps reappearing without ever
   being forged, exactly the anti-staleness intent. (No per-fact KG
   timestamps are available from `ask_tesserae`, so decay is keyed on our
   own `first_seen_at` ledger — honest and deterministic.)
3. **Dedup is two-layered.** (a) `signal_id = sha256(project_id|question|
   normalized_content)` is the PRIMARY KEY of `harness_kg_signals`;
   re-capture UPSERTs (preserves `first_seen_at`, refreshes `captured_at`).
   (b) `already_forged`: if the signal's normalized content is a soft
   substring-overlap of any **currently-bound** primitive's content
   (passed in via `forged_index`), set `already_forged=True` and force
   `weight=W_MIN` (don't re-propose what's already built).
4. **No round_id ordering hazard.** Signals persist at gather time with
   `round_id=NULL` (the round doesn't exist yet). The round's
   `input_kg_signals_json` snapshot is the authoritative per-round record;
   `harness_kg_signals` is a dedup/decay ledger keyed by `signal_id`.
   `round_id` column stays nullable, optionally backfilled — but we do NOT
   thread it through (keeps gather order intact). Drop it from scope if it
   complicates; the snapshot suffices.
5. **Fail-open, best-effort.** Every `ask_tesserae` call and the whole
   gather is wrapped so any failure yields `[]` — a KG outage NEVER blocks
   an evolution round. Gated hard on `get_tesserae_root is not None`.
6. **Backend-only.** No frontend in E2 (the round detail already renders
   `input_*` JSON generically; a dedicated KG-signal panel is deferred and
   noted, per the "no silent scope creep" rule).
7. **All-backend note:** `ask_tesserae` is a CLI shell-out (not an LLM
   provider call), so the per-backend `{backend_kind, model_override}` rule
   does not apply here — the *graph* is the source, the harness that
   compiled it is irrelevant to consumption. State this in the task so the
   reviewer doesn't flag it.

## Tasks (TDD, fresh subagent each, spec + quality review per task)

### Task 1 — `KGSignalItem` model + `harness_kg_signals` table + repo
- **Model** (`app/models/harness_evolution.py`, append): `KGSignalItem`
  (Pydantic v2) — `signal_id: str`, `project_id: str`, `question: str`,
  `content: str`, `weight: float` (Field ge=0.3 le=0.7), `already_forged:
  bool=False`, `first_seen_at: str`, `captured_at: str`. Mirror the file's
  existing model style.
- **Schema** `app/db/schema/_harness_kg_signals.py`: `CREATE TABLE IF NOT
  EXISTS harness_kg_signals (signal_id TEXT PRIMARY KEY, project_id TEXT
  NOT NULL, round_id TEXT, question TEXT NOT NULL, content TEXT NOT NULL,
  weight REAL NOT NULL, already_forged INTEGER NOT NULL DEFAULT 0,
  first_seen_at TEXT NOT NULL, captured_at TEXT NOT NULL)` +
  `CREATE INDEX IF NOT EXISTS idx_hks_project ON harness_kg_signals(project_id)`.
  Register in `app/db/schema/__init__.py` `create_fresh_schema` (follow how
  `_forge_promotion` was registered in E1).
- **Repo** `app/db/harness_kg_signals.py`:
  - `_ensure_kg_signal_tables(conn)` — CREATE TABLE/INDEX IF NOT EXISTS
    (runtime-safe for existing DBs).
  - `record_signal(*, signal_id, project_id, question, content, weight,
    already_forged, now)` — UPSERT: INSERT … ON CONFLICT(signal_id) DO
    UPDATE SET captured_at=excluded.captured_at, weight=excluded.weight,
    already_forged=excluded.already_forged, content=excluded.content
    (first_seen_at PRESERVED). Returns the stored row dict.
  - `get_signal(signal_id)`, `list_signals(project_id, *, limit=50)`
    (newest captured first), `first_seen_at_for(signal_id) -> Optional[str]`.
- **Migration** `app/db/migrations/v07_features.py`: new `_migrate_122`
  (next free number — VERIFY the current max in that file) — CREATE TABLE
  + INDEX IF NOT EXISTS. Register in the migration list exactly like
  E1's `_migrate_121`.
- **Tests** `backend/tests/test_harness_kg_signals_repo.py`: upsert
  preserves first_seen_at + refreshes captured_at/weight; list ordering;
  idempotent ensure; migration creates table.

### Task 2 — KG signal gathering service
- `app/services/harness_kg_signals.py`:
  - Constants `W_MAX=0.7, W_MIN=0.3, HALF_LIFE_DAYS=30.0`,
    `_DISCOVERY_QUESTIONS` (tuple of 3, see decision 1).
  - `_norm(text) -> str` (lower, collapse whitespace) for fingerprinting +
    overlap.
  - `compute_weight(first_seen_at, now) -> float` — clamp decay (decision 2).
    Parse timestamps with the project's standard fmt (`"%Y-%m-%d %H:%M:%S"`
    — SQLite space-separated, the D-phase T-vs-space bug; reuse the existing
    helper if one exists, else parse defensively and fail to W_MAX on
    unparseable).
  - `_compute_signal_id(project_id, question, content) -> str` (sha256 hex).
  - `gather_kg_signals(project_id, *, forged_index=None, now=None) ->
    list[KGSignalItem]`:
    1. `root = get_tesserae_root(project_id)`; `None` ⇒ return `[]`.
    2. `now = now or <utcnow space-fmt>`.
    3. For each question: `try: ans = ask_tesserae(project_id, q, top_k=5)`
       (best-effort, continue on None/exception). Skip blank/whitespace
       answers.
    4. `content = ans.strip()`; `sid = _compute_signal_id(...)`.
    5. `first = first_seen_at_for(sid) or now`; `w = compute_weight(first, now)`.
    6. `already_forged`: if `forged_index` and any `_norm(primitive_content)`
       shares a long-enough overlap with `_norm(content)` (e.g. one contains
       a ≥ 60-char slice of the other) ⇒ `True`, `w = W_MIN`.
    7. `record_signal(...)`; build `KGSignalItem`. Append.
    - Whole body in an outer try/except ⇒ `[]` on catastrophic failure;
      log at warning. NEVER raises.
- **Tests** `backend/tests/test_harness_kg_signals_service.py` (monkeypatch
  `ask_tesserae` + `get_tesserae_root` + `record_signal`/`first_seen_at_for`):
  disabled-project ⇒ []; happy path builds N items with weight 0.7 on first
  sight; re-capture with old first_seen_at ⇒ decayed weight; already_forged
  ⇒ weight floored to 0.3 + flag set; ask_tesserae None/raises ⇒ that
  question skipped, others survive; blank answer skipped; weight always in
  [0.3, 0.7].

### Task 3 — round column `input_kg_signals_json` + persist
- **Schema** `_harness_evolution.py` CREATE TABLE: add
  `input_kg_signals_json TEXT NOT NULL DEFAULT '[]'` (place near
  `input_forge_json`).
- **Repo** `harness_evolution.py`:
  - Add `"input_kg_signals_json"` to `_ROUND_COLUMNS_IN_ORDER` (so the
    C1 table-recreate migration preserves it).
  - New `_ensure_kg_signals_column(conn)` as the OUTERMOST link: it calls
    `_ensure_autonomy_columns(conn)` first, then PRAGMA-guarded
    `ALTER TABLE … ADD COLUMN input_kg_signals_json TEXT NOT NULL DEFAULT
    '[]'`. Repoint the existing ensure-chain entrypoint(s) (every caller
    that currently calls `_ensure_autonomy_columns`) to call
    `_ensure_kg_signals_column` instead — GREP for `_ensure_autonomy_columns(`
    callers and update them.
  - `start_round`: add param `input_kg_signals: Optional[list] = None`
    (default ⇒ `[]`), JSON-dump into the INSERT (extend the column list +
    VALUES + tuple). Keep backward-compat (param optional, trailing).
- **Migration** `v07_features.py` `_migrate_122` (or a sibling): add
  `input_kg_signals_json` via PRAGMA-guarded ALTER for existing DBs AND in
  the round-table CREATE block at `:765` if that block recreates the table.
  Mirror how `input_forge_json` appears there.
- **Tests** `backend/tests/test_harness_evolution_kg_column.py`: fresh
  schema has the column defaulting `'[]'`; `start_round(input_kg_signals=
  [...])` round-trips the JSON; `_ensure_kg_signals_column` idempotent on a
  DB that predates the column; the C1 recreate path preserves it (build an
  old-CHECK table, run the ensure-chain, assert column + data survive).

### Task 4 — wire `gather_inputs` + surface in workspace
- `harness_evolver.py` `gather_inputs`: after takeaways, add
  ```python
  try:
      from app.services.harness_kg_signals import gather_kg_signals
      forged_index = [
          (p["asset"].get("content") or "")
          for plist in primitives.values() for p in plist
      ]
      kg_signals = [
          s.model_dump()
          for s in gather_kg_signals(project_id, forged_index=forged_index)
      ]
  except Exception:
      kg_signals = []
  ```
  and add `"kg_signals": kg_signals` to the returned dict.
- Call site `:1432` `start_round(...)`: pass
  `input_kg_signals=inputs.get("kg_signals") or []`.
- **Workspace surfacing** (`build_workspace`): write `KG_SIGNALS.md`
  listing each signal (`weight`, `already_forged`, `question`, `content`)
  sorted by weight desc, with a one-line header telling Codex these are
  KG-discovered candidates to consider for new rules/hooks/commands/skills.
  Skip the file when `kg_signals` is empty. Reference it from the PROMPT or
  DESIGN guide so Codex actually reads it (mirror how trajectories/takeaways
  are referenced). Do NOT disturb `_build_tesserae_context_md`.
- **Tests** `backend/tests/test_harness_evolver_kg_inputs.py` (monkeypatch
  `gather_kg_signals`): `gather_inputs` includes `kg_signals`; gather
  failure ⇒ `kg_signals == []` and rest intact; `build_workspace` writes
  `KG_SIGNALS.md` with the content when present and omits it when empty;
  the start_round snapshot carries the signals (integration-ish with a
  fake repo or the isolated_db).

### Task 5 — verification gate
- `cd backend && uv run pytest -q` (full suite, redirect to
  `~/e2_full_suite.txt`). PASS criterion: only the **3 known pre-existing
  failures** (`test_provider_usage_client` claude-remediation text +
  `test_schema_split` table/index parity — E2 adds 1 table + 1 index +
  1 round column, widening the already-stale parity drift; this is the
  same accepted baseline gap as A–E1, NOT a regression). Zero green→red.
- `cd backend && uv run ruff format .` (line-length 100).
- No frontend changes ⇒ `just build` / `npm run test:run` only if any FE
  file was touched (it should not be). Confirm `git diff --stat` is
  backend + docs only.

## Review protocol (per the subagent-driven-development skill)
Each task: failing test → impl → `uv run pytest <file>` green → commit.
Then spec-compliance review + code-quality review; fix→re-review loop.
After all 5: ONE holistic whole-implementation review (opus) over the full
E2 diff — specifically probe: (a) can a KG outage or malformed `ask`
output ever break a round? (b) is the decay monotonic + bounded in
[0.3,0.7] for all inputs incl. clock skew / unparseable timestamps?
(c) does the C1 recreate path still preserve every round column incl. the
new one? (d) any unbounded LLM fan-out (must be ≤ 3 ask calls/round)?
(e) does `already_forged` ever mis-floor a genuinely-new signal? Fix any
Important/Critical, re-review, THEN finish-the-branch (FF local merge to
main, delete branch). Merge stays LOCAL (main already 70 ahead of origin,
unpushed). Do NOT touch the pre-existing uncommitted working-tree mods.

## Done = whole life-harness done
E2 is the final edge. On merge, all 6 loop stages — capture → annotate/
extract → **KG-seeded** gather → propose → eval-gate → apply (operator or
autonomous) → materialize → rollback → **propagate** → KG — are 100%.
Update `project_life_harness_completion.md` + `MEMORY.md` to mark the
life-harness COMPLETE.
