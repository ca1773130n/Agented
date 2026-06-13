---
phase: 21
wave: all
plans_reviewed: [21-01, 21-02, 21-03, 21-04, 21-05, 21-06, 21-07, 21-08]
timestamp: 2026-06-13T00:00:00Z
blockers: 0
warnings: 2
info: 3
verdict: warnings_only
status: warnings_only
---

# Code Review: Phase 21 — One-click team harness setup (all waves)

## Verdict: WARNINGS ONLY

The 6-step orchestrator, persistence floor, route trio, and operator surface
are correct, idempotent, and free of destructive deletes. Two non-blocking
warnings: a latent policy_json key mismatch (dead branch, currently safe) and
the fire-and-forget grd_init step that records "ok" before init completes
(documented as deferred-dogfood D1).

## Stage 1: Spec Compliance

### Plan Alignment
No issues. Every plan (21-01..08) has feat+test+docs commits in `main..HEAD`;
SUMMARY claims match the diff. All 28 backend + 4 frontend phase tests pass.

### Research Methodology — sharp edges all handled
- SA-instance dedup (P1): `_step_team_topology` existence-checks via
  `get_project_sa_instances_for_project` BEFORE `create_team_instances`
  (team_harness_setup_service.py:222-237). No duplicate rows on re-run. PASS.
- `driver=grd` post-create reconcile (P2): set on EVERY instance on both the
  create AND skip path (lines 239-243), guarded by a `get_instance_driver`
  read. Converges on re-run. PASS.
- No destructive deletes (SC4): grd_init reconcile-skips a populated
  `.planning/` (line 180); bundle binding goes only through idempotent
  `bind_bundle_to_project` upsert (line 330); tesserae never calls
  `unset_*`; policies use ON CONFLICT upsert; materialize relies on the
  `_NEVER_DELETE` guard. No DELETE/unbind anywhere. PASS.

### Dual-consumer autonomy policy (Seam 5 / P7) — see WARNING-1
`_default_autonomy_policy` is conservative (allowed_kinds=
['discovered_procedure'], block_deletes, max_ops_per_round=1, enabled=True).
The conservative evolution gate `autonomous_apply_eligible` reads
`policy.allowed_kinds` directly off the validated model (harness_autonomy.py:93)
— correctly scoped. The takeaway gate `_auto_apply_policy` returns True on
enabled=True (intended ON). Both consumers behave correctly. The `kinds`
key path is dead code — WARNING-1.

### Eval Coverage
21-06 ships a 4-backend golden renderer_compile test; step f compile-smoke
exercises all four `_COMPILE_BACKENDS`. Eval is computable. PASS.

## Stage 2: Code Quality

### Architecture
Consistent. Route trio mirrors the grd-chat thread-spawn + trace-SSE Stream
patterns; DB helpers mirror upsert_policy; api client follows the
`src/services/api` package layout and is barrel-exported. PASS.

### Reproducibility / Threading
`setup()` runs on a daemon thread; `auto_init_project` spawns its own nested
daemon thread and returns immediately. Each DB call uses a fresh
`get_connection()` context manager — no shared connection across threads.
Status flips: route sets "running" eagerly, `setup()` re-sets "running" then
"ready"/"failed"; catch-all guard converts any crash to "failed". Re-run
skips already-"ok" steps and resumes from the first non-ok. PASS.

### Documentation
Module + step docstrings cite seam/pitfall numbers and source file:line
anchors. ruff clean (line-length=100). PASS.

### Deviation Documentation
SUMMARY.md files match git history; 21-08 discloses the deferred D1 dogfood.

## Findings Summary

| # | Severity | Stage | Area | Description |
|---|----------|-------|------|-------------|
| 1 | WARNING | 1 | Autonomy policy | `_auto_apply_policy` reads `policy_json["kinds"]` but `AutonomyPolicy` serializes `allowed_kinds`; the kind-scope branch is dead — falls through to `return True` on enabled=True |
| 2 | WARNING | 2 | grd_init step | Step a records "ok" ("init triggered") for a fire-and-forget background init that may still fail; overall status can read "ready" before GRD init actually finishes |
| 3 | INFO | 2 | SSE | `harness_setup_stream` is `async def` with `sync_to_thread=False` → benign LitestarWarning (matches existing stream_trace) |
| 4 | INFO | 2 | SSE | Stream polls DB every 1s for up to 10 min; acceptable but a long-lived per-connection poll loop — fine at single-operator scale |
| 5 | INFO | 1 | Idempotency | A fully-successful prior run skips all 6 steps and flips straight to "ready" — correct and intended |

## Recommendations

- WARNING-1: Make the takeaway gate robust by reading `allowed_kinds` (the
  actual serialized key) in `_auto_apply_policy`, OR drop the dead `kinds`
  branch and document that enabled=True alone arms takeaway auto-apply. Today
  it is safe because the conservative evolution gate is a separate reader that
  uses the validated model — but the dead branch will mislead a future editor
  who assumes per-kind scoping is enforced on the takeaway path.
- WARNING-2: This is the documented D1 deferred dogfood. Before relying on
  "ready" as a real completion signal, gate step a on actual init completion
  (or surface grd_init_status separately) so the chip does not over-report.
