# GRD Patterns → GENOME-SUGGESTIONS → Promote — Design

**Milestone:** "Wire GRD 0.4.5 + Tesserae 0.9.0" → sub-project #4 of 4 (final).
**Branch:** `feat/grd-life-harness-wiring`.
**Date:** 2026-06-15

## Goal

Wire GRD 0.4.1+ deterministic pattern mining into Agented: mine statistically
significant heuristics from a project's REFLECTION.md history, persist + surface
them as promotable suggestions, and promote a chosen one into `GENOME.md`.

## Grounding (verified against installed `gd` v0.4.5)

- `gd patterns [--apply --yes] [--min-occurrences N] [--effect-size F]
  [--fdr-q F]` — scans `REFLECTION.md`, runs binomial + Benjamini-Hochberg FDR,
  returns `PatternsResult { reflections_scanned, baseline_confirmed_rate,
  tokens_tested, suggestions: TokenStat[], applied, suggestions_path }`. Dry-run
  by default; `--apply --yes` writes `.planning/GENOME-SUGGESTIONS.md`.
  `TokenStat { token, n, confirmed, confirmed_rate, baseline, effect_size,
  raw_p, fdr_q, significant }`. The promote slug for a suggestion is
  `` `${token}-rate` ``.
- `gd genome promote-suggestion <slug>` — copies the suggestion's heuristic into
  `GENOME.md` "Heuristics in use (promoted)"; returns
  `{promoted, heuristic, genome_path}`. Requires `GENOME-SUGGESTIONS.md` to
  exist (so `--apply --yes` must run first).

### CLI gotcha (verified empirically — drives the runner)
grd-tools' output convention is **inverted**: `gd patterns` with **no flag
emits JSON**; `--json`/`--raw` emit human text; **errors exit 0**. Agented's
existing `run_command` appends `--raw` (→ human), so it cannot be reused. The
runner invokes with **no output flag**, parses stdout JSON, and treats an
`Error:`-prefixed or unparseable body as failure (since exit code is unreliable).

## Design

### Backend
1. **Migration 168** `grd_genome_suggestions` + register; `gsug-` id helper.
   Table (one row per project — latest run, full-replace upsert):
   `id, project_id FK, reflections_scanned, baseline_confirmed_rate,
   tokens_tested, suggestions_json, applied, suggestions_path, created_at,
   updated_at`, UNIQUE`(project_id)`.
2. **DB module** `app/db/grd_genome_suggestions.py`:
   `upsert_genome_suggestions(...)`, `get_genome_suggestions(project_id)`,
   `_row_to_dict` (parses suggestions_json). Exported via `app/db/__init__.py`.
3. **Runner** `app/services/grd_genome_patterns_runner.py`:
   - `_run_gd_plain(cwd, *args) -> {success, data, error}` — invokes the gd
     binary with NO output flag (via the resolved gd path, like
     `grd_harness_round_runner._gd_cmd`), strips stdout, fails on an `Error:`
     prefix or JSON-parse failure.
   - `mine_patterns(project_id, cwd, *, apply, min_occurrences, effect_size,
     fdr_q)` → `gd patterns [--apply --yes] [--min-occurrences N]
     [--effect-size F] [--fdr-q F]`; on success mirrors the result into
     `grd_genome_suggestions`; returns `{success, data, error, mirrored}`.
   - `promote_suggestion(cwd, slug)` → `gd genome promote-suggestion <slug>`
     (no mirror — `GENOME.md` is the record); returns `{success, data, error}`.
4. **Routes** in `grd_routes.py` (register in `grd_router`):
   - `POST /{id}/grd/genome/patterns` body
     `{apply?, min_occurrences?, effect_size?, fdr_q?}` → mine_patterns.
   - `GET /{id}/grd/genome/suggestions` → mirrored latest run (404 if none).
   - `POST /{id}/grd/genome/promote-suggestion` body `{slug}` → promote_suggestion.

### Frontend (inside the existing GenomePanel)
5. `grdHarnessApi`: `minePatterns(projectId, opts)`,
   `getGenomeSuggestions(projectId)`, `promoteSuggestion(projectId, slug)`
   + `GenomeSuggestionsResult` / `TokenStat` types.
6. **GenomePanel.vue** "Patterns → Suggestions" section: "Mine (preview)"
   (`apply:false`) + "Mine & save" (`apply:true`); loads the mirrored run on
   mount; suggestions list (token, confirmed % vs baseline, effect size,
   fdr_q, significant) each with a **Promote** button (slug `` `${token}-rate` ``,
   enabled only when the suggestions file was saved). i18n under
   `surface.harness.panels.genome.patterns.*` (en/ko/ja/zh, key-identical).
7. Update `harness-panels.test.ts`: add `minePatterns` / `getGenomeSuggestions`
   / `promoteSuggestion` to the mocked `grdHarnessApi` so GenomePanel mounts
   (the "16 routes" coverage assertion is unchanged — these are additive).

## Scope / non-goals
- Deterministic CLI wiring only (no LLM).
- Promote does not track promoted-state in the mirror (GENOME.md is the truth;
  the UI re-reads `genome show`).
- `min_occurrences`/`effect_size`/`fdr_q` exposed with GRD's defaults
  (10 / 0.2 / 0.1) — overridable via the request body but no UI knobs in v1.

## Tests
- Backend: mine_patterns argv (apply on/off, knob flags) + mirror-on-success;
  JSON parse; `Error:`-prefix → failure; promote_suggestion argv + error path;
  DB upsert/get round-trip.
- Frontend: GenomePanel mounts (updated mock); Mine calls minePatterns and
  renders suggestions; Promote calls promoteSuggestion with `<token>-rate`.

## Verification
`just build`; backend targeted pytest (new suite + grd route/db/migration
regressions); frontend `npm run test:run` (no new failures vs the 7 baseline).
