---
phase: 17
wave: all
plans_reviewed: [17-01, 17-02, 17-03, 17-04, 17-05, 17-06]
timestamp: 2026-06-13T00:00:00Z
blockers: 0
warnings: 2
info: 4
verdict: warnings_only
status: warnings_only
---

# Code Review: Phase 17 (Forge Creation Surface) — all 6 plans

## Verdict: WARNINGS ONLY

All six plans executed, 24 commits map cleanly to plan tasks. Migration numbering
(155/156/157) is unique and contiguous above the prior max (154). The
security-critical 17-06 session-import gate fails closed correctly. Two WARNINGs
concern operator-file overwrite-on-reimport and absence of content sanitization
on injected subagent bodies; neither blocks the phase.

## Stage 1: Spec Compliance

### Plan Alignment
No issues. Each plan's SUMMARY tasks correspond to commits (17-01 fix+test,
17-02 table+CRUD+routes, 17-03 bundles+_add_binding, 17-04 materialize+4 renderers,
17-05 service+routes, 17-06 seed+origin+import handler).

### Research Methodology
- 17-04 four-backend parity is faithful to RESEARCH.md: claude discovers
  subagents NATIVELY from the overlay `agents/` dir (no inline); codex/gemini/
  opencode use the documented degrade-path prompt-prefix block. Asymmetry is
  intentional and documented inline. Correct.
- 17-06 session_kind set matches RESEARCH Open Q1; global-scope bundle decision
  (Open Q2) and _add_binding sync (Open Q3) honored.

### Known Pitfalls / Distinctness
- 17-02: `subagents` table is genuinely DISTINCT from the legacy `agents` table
  — separate migration 155, `subag-` id prefix, separate CRUD module, no shared
  writes. No collision. PASS.
- 17-03: skill_sets / skill_set_items are NOT touched by migration 156 (verified
  in diff). PASS.

### Eval Coverage
N/A for code-review stage (17-EVAL.md present; VERIFICATION runs later).

## Stage 2: Code Quality

### Architecture
- Route handlers follow the existing `caller: Caller` + `del caller` pattern
  (auth enforced by ApiKey/bearer middleware). Consistent.
- `_add_binding` upsert SQL mirrors `add_binding`. INFO below on conflict_policy.

### 17-05 Atomic Compensation — verified correct
LIFO compensation undoes written files → manifest reconcile → binding → asset
row, in reverse of forward order. Every step wrapped in its own try/except; the
original exception is re-raised after `_compensate` (the bare `raise` in the
outer handler). No orphan row/binding/file remains at any failure stage. The
bundle-bind route binds all items in ONE `get_connection()` block and only
commits at the end, so a mid-loop raise rolls back the whole bind. Sound.

### Reproducibility / Idempotence
- 17-06 seed is idempotent (existence-guarded on skill name, bundle name, bundle
  item; returns created=False on no-op). PASS.
- forge_origin upsert keyed on (asset_id, kind) with hash idempotence. PASS.

### Documentation
Adequate — module docstrings explain the security rationale, the
no-saga compensation strategy, and the renderer asymmetry.

### Deviation Documentation
SUMMARY files match git history.

## Findings Summary

| # | Severity | Stage | Area | Description |
|---|----------|-------|------|-------------|
| 1 | WARNING | 1 | 17-06 operator-overwrite | A *changed* session-scaffolded `.claude/agents/<n>.md` is re-imported AND re-materialized, rewriting the operator's file in place (Agented frontmatter re-emitted). Operator body content is preserved but their exact file form is overwritten; the plan asked that operator-modified artifacts not be overwritten. |
| 2 | WARNING | 2 | 17-06 injection | Imported subagent body is stored verbatim and inlined into codex/gemini/opencode degrade-path system prompts with no content sanitization. The session_kind gate is the sole mitigation; trusted-but-not-verified content from a compromised Agented session still reaches the prompt. |
| 3 | INFO | 2 | conflict_policy drift | `add_binding` relies on the column DEFAULT 'local_wins'; `replace_for_project` and `_add_binding` write it explicitly. Values converge, but three write paths handle the column differently — worth a shared constant. |
| 4 | INFO | 1 | gate fail-closed | 17-06 gate returns BEFORE any filesystem access on unknown/foreign session_kind. Correctly fail-closed. Positive observation. |
| 5 | INFO | 2 | get_origin_by_hash unused | `forge_origin.get_origin_by_hash` is defined but the import handler uses name-keyed `get_origin` only. Dead-ish helper; harmless. |
| 6 | INFO | 1 | bundle-bind no project-membership check | bundle-bind binds any bundle_id to any project after `_ensure_project`; bundle ownership/scope not re-validated. Acceptable for admin-scoped route. |

## Recommendations

1. (WARNING #1) Before re-materializing a changed import, check
   `forge_origin` for prior provenance and skip re-write when the on-disk file
   has no Agented frontmatter marker (i.e. operator authored it fresh), or gate
   re-materialize behind an explicit "managed" flag so operator hand-edits are
   not silently rewritten. At minimum, document the rewrite-in-place behavior.
2. (WARNING #2) Add a lightweight sanitization/escaping pass (or a clearly
   delimited, non-instruction-framed block) when inlining imported subagent
   bodies into degrade-path prompts, and note the residual trust assumption in
   KNOWHOW.md.
3. (INFO #3) Extract a shared `DEFAULT_CONFLICT_POLICY = "local_wins"` constant
   used by all three write paths.
