# GRD Multi-Candidate Plan Selection — Design

**Milestone:** "Wire GRD 0.4.5 + Tesserae 0.9.0" → sub-project #3 of 4.
**Branch:** `feat/grd-life-harness-wiring`.
**Date:** 2026-06-15

## Goal

Wire GRD 0.4.5's **deterministic plan-candidate selection** into Agented: given
a phase that has `PLAN-1.md … PLAN-K.md` candidates, let an operator score them
(dry-run preview), promote the winner to `PLAN.md`, and mirror the
`PLAN-SELECTION.json` audit — all from the planning page, per phase.

## Grounding (verified against installed `gd` v0.4.5)

- **Generation is LLM-driven, NOT a CLI generator.** `gd plan-phase <N>
  --candidates K` *parses* a planner agent's `<<<PLAN-i>>>` marker blocks into
  `PLAN-1.md…PLAN-K.md`. Generation belongs to the `/grd:plan-phase` agent,
  which Agented already runs via its PTY planning session. **Out of scope.**
- **Selection is deterministic, no LLM:**
  - `gd select-candidate <N> [--dry-run] [--force] [--run-verification-commands]
    [--json]` — reads `PLAN-N.md` candidates from
    `.planning/milestones/<ms>/phases/<NN-name>/`, scores base axes
    (completeness/goal_alignment/hypothesis_quality/conciseness) + extended
    (must_haves coverage, optional verification_commands, cost tiebreak),
    applies DEAD-ENDS hard-fail + proximity clustering, promotes the winner
    `PLAN-N.md → PLAN.md` (unless `--dry-run`), writes `PLAN-SELECTION.json`.
    Emits the full `SelectionResult` JSON (`candidates[]`, `winner`,
    `promoted_to`, `audit_trail_path`).
  - `gd plan-tournament --phase <N> --candidates <paths…> [--json]` — simpler
    ranked scorer over explicit paths; no promotion, no audit.
- `--run-verification-commands` runs planner-authored commands — **off by
  default** (security). `--force` overwrites an already-resolved `PLAN.md`.

## Design

### Backend
1. **Migration 167** `_migrate_167_grd_plan_selections` + register: table
   `grd_plan_selections` (id `psel-`, project_id FK, phase TEXT, milestone TEXT,
   winner_rel TEXT, promoted_to TEXT, candidates_json TEXT, audit_json TEXT,
   created_at/updated_at) UNIQUE`(project_id, phase)`; index on
   `(project_id, created_at DESC)`. `psel-` id helper in `ids.py`
   (`_get_unique_plan_selection_id`) mirroring `_get_unique_harness_round_id`.
2. **DB module** `app/db/grd_plan_selections.py`:
   `upsert_plan_selection(...)` (full-replace on `(project_id, phase)`, returns
   `psel-` id), `get_plan_selection(project_id, phase)`,
   `list_plan_selections(project_id, limit)`, `_row_to_dict` (parses
   candidates_json/audit_json). Exported via `app/db/__init__.py`.
3. **Runner** `app/services/grd_plan_selection_runner.py` (synchronous —
   selection is sub-second):
   - `select_candidate(project_id, cwd, phase, *, dry_run, force,
     run_verification_commands) -> dict` → builds `gd select-candidate <phase>`
     argv (+ flags) via `GrdCliService.run_gd_json`; on a real (non-dry-run)
     success mirrors to `grd_plan_selections`; returns
     `{success, data, error, mirrored}`.
   - `plan_tournament(cwd, phase, candidate_paths) -> dict` →
     `gd plan-tournament --phase <N> --candidates <paths…>` via run_gd_json
     (no mirror).
4. **Routes** in `grd_routes.py` (register in `grd_router`):
   - `POST /{project_id}/grd/plan/{phase}/select` body
     `{dry_run?, force?, run_verification_commands?}` → runner.select_candidate;
     surfaces gd's "no PLAN-N.md candidates" as a 400.
   - `GET /{project_id}/grd/plan/{phase}/selection` → mirrored row (404 if none).
   - `POST /{project_id}/grd/plan/tournament` body `{phase, candidates:[paths]}`
     → runner.plan_tournament.

### Frontend
5. **API client** `services/api/grdPlanning.ts`: `PlanCandidate`/`PlanSelection`
   types + `grdPlanningApi.selectCandidate(projectId, phase, opts)`,
   `getSelection(projectId, phase)`, `planTournament(projectId, phase, paths)`.
   Re-export via the api `index.ts` barrel.
6. **Panel** `components/grd/PlanSelectionPanel.vue` — mounted **per phase**
   inside `MilestoneOverview`'s phase-card (add a `projectId` prop to
   MilestoneOverview, passed from ProjectPlanningPage). Collapsible; "Score
   (dry-run)" → ranked candidate list (score + per-axis breakdown + DEAD-ENDS
   hard-fail badge + cluster/merged indicator + winner highlight); "Select &
   promote" → real run (then shows promoted_to). Loads the mirrored selection
   on expand. i18n `grdPlanSelection` namespace (en/ko/ja/zh, key-identical).

## Scope / non-goals
- NOT re-implementing LLM candidate generation (planning session owns it).
- verification_commands axis off unless explicitly toggled (security).
- No changes to existing phases/plans endpoints; this is additive.

## Tests
- Backend: select_candidate argv (dry-run vs promote, force, verification
  flags) + mirror-on-real-run-only; plan_tournament argv; DB upsert/get
  round-trip + JSON parse; route happy-path + no-candidates error
  (run_gd_json mocked).
- Frontend: PlanSelectionPanel calls selectCandidate on dry-run + real,
  renders ranked candidates + winner, surfaces the no-candidates error.

## Verification
`just build`; backend targeted pytest (new suite + grd route/db/migration
regressions); frontend `npm run test:run` (no new failures vs the 7 baseline).
