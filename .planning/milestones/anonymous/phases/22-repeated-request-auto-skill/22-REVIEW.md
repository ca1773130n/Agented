---
phase: 22
wave: all
plans_reviewed: [22-01, 22-02, 22-03, 22-04, 22-05, 22-06]
timestamp: 2026-06-13
blockers: 1
warnings: 3
info: 3
verdict: blocker_found
---

# Code Review: Phase 22 (Repeated-request auto-skill) — all plans

## Verdict: BLOCKERS FOUND

Security scanner is genuinely fail-closed and the UPSERT invariants hold. One
provenance round-trip bug breaks the overwrite guard on every legitimate
re-run; several non-blocking hardening gaps.

## Stage 1: Spec Compliance

### Plan Alignment
All 6 plans have matching commits + SUMMARY files. No missing tasks.
VERIFICATION/EVAL-RESULTS correctly deferred (not flagged).

### Research / Known Pitfalls / Eval Coverage
Cosine 0.83, occ>=3, fail-closed scan match RESEARCH grounding. A1 embed-disabled
and P1 paraphrase eval criteria are computable against detect_for_session. OK.

## Stage 2: Code Quality — ISSUES FOUND

### BLOCKER 1 — provenance origin_hash never matches on-disk SKILL.md
`repeated_request_gate.py:244-248` records `origin_hash=content_hash(skill_content)`
(raw body), but `_create_skill` writes `_render_skill_md(name, payload)` to disk —
frontmatter wrapped around the body (`harness_evolver.py:1418-1428, 1474`). So
`provenance_allows_overwrite` (`skill_safety_scanner.py:187-192`) re-hashes the
wrapped file and compares to the bare-body hash: they NEVER match. Every
auto-created skill is seen as "operator-edited" on the next gate run, permanently
downgrading its own patch path to PROPOSE — the AUTO->patch loop can never fire
twice. Fail-closed direction is safe, so correctness blocker, not a security hole.
FIX: hash exactly what lands on disk:
`origin_hash=content_hash(ev._render_skill_md(skill_name, payload))`, and have
provenance_allows_overwrite read/compare the same rendered form.

### WARNING 1 — convert_signal AUTO path not idempotent (create-once not guarded)
`repeated_request_gate.py:204,250`: nothing reads `signal.skill_created` before the
AUTO branch. A second drive of the same signal re-runs `_create_dispatch['skill']`;
_create_skill dedups files by name, but a second `discovered_procedure` takeaway is
inserted and origin re-recorded. Docstring claims "create exactly once".
FIX: early-return when `getattr(signal,'skill_created',False)` before the takeaway insert.

### WARNING 2 — detector embeds on every completion; unbounded match scan
`repeated_request_detector.py:121,86-89`: `embed_text` + `_match_existing` load ALL
project signals (`list_signals` has no LIMIT) and run a full cosine batch on every
session completion, in the bus thread. Non-blocking but a latency/cost risk that
grows with signal count.
FIX: cap candidates (top-N by occurrence_count) or cheap pre-filter before embedding.

### WARNING 3 — scanner has no input size cap
`skill_safety_scanner.py:76-77,115` runs bounded-quantifier regexes on untrusted
skill_content with no length guard. Not true ReDoS, but add a size cap (reject/
truncate > N KB) before scanning to bound worst-case cost.

### INFO 1 — UPSERT invariants verified correct
`first_seen_at` INSERT-only (DO UPDATE omits it, repeated_request_signals.py:91-96);
occurrence_count strictly +1; FIFO cap correct (_fifo_merge:47-51). All queries
parameterized; list_signals WHERE built from fixed literals — no SQLi. PRIMARY KEY
on request_hash backs ON CONFLICT.

### INFO 2 — safety scanner genuinely fail-closed
Invisible-Unicode sweep covers zero-width/bidi/word-joiner/tag ranges; any match =>
unsafe. provenance unreadable => refuse. Gate downgrades scan/provenance failures to
PROPOSE, never silently AUTO. No bypass found in swept ranges.

### INFO 3 — gate matrix + non-blocking confirmed
evaluate_signal pure; AUTO requires occ>=3 AND within 30d AND verified>=1 AND scan AND
provenance AND policy. Detector self-registration idempotent and isolated by
emit_session_complete per-handler try/except (execution_events.py:55-62); lifecycle
block has its own try/except.

## Findings Summary

| # | Severity | Stage | Area | Description |
|---|----------|-------|------|-------------|
| 1 | BLOCKER | 2 | Provenance | origin_hash(body) != hash(rendered SKILL.md) -> guard always refuses |
| 2 | WARNING | 1 | Gate idempotency | AUTO not guarded on skill_created; double takeaway |
| 3 | WARNING | 2 | Resource | Unbounded list_signals scan + embed per completion |
| 4 | WARNING | 2 | Resource | No size cap on scanned skill_content |

## Recommendations
1. (BLOCKER) Hash the rendered SKILL.md for origin_hash, not the bare body.
2. (WARNING) Guard convert_signal AUTO on skill_created for create-once.
3. (WARNING) Bound list_signals scan + add skill_content size cap before scan.

## Re-review (post-fix)

Commit dae96043b1 verified against current source. All 4 findings genuinely resolved; no new issues. 39/39 tests pass (`test_repeated_request_gate.py` + `test_skill_safety_scanner.py`).

### VERIFICATION PASSED

**BLOCKER (origin_hash over rendered SKILL.md) — RESOLVED.**
`repeated_request_gate.py:259` records `content_hash(ev._render_skill_md(written_name, payload))`.
- Create path: `written_name = skill_name` (line 249); `_create_skill` writes `_render_skill_md(name, payload)` (`harness_evolver.py:1474`) with `name == skill_name`. Hash matches disk.
- Patch path: `written_name = dedup_existing["skill_name"]` (line 244); `_update_skill` writes `_render_skill_md(row["skill_name"], payload)` (`harness_evolver.py:1537`) where `row = get_user_skill(asset_id)` and `asset_id = dedup_existing["id"]`. Since `dedup_existing` is a `user_skills` row, `dedup_existing["skill_name"] == row["skill_name"]`. Hash matches disk. No residual mismatch.

**W1 (idempotent re-drive) — RESOLVED.** Guard at `repeated_request_gate.py:210` (`if getattr(signal, "skill_created", 0)`) is correctly placed after the `route != "auto"` return (line 204) and before the takeaway insert (line 217). Re-drive short-circuits with zero creates, zero updates, zero takeaway inserts. Confirmed by `test_convert_idempotent_when_already_created`.

**W2 (bounded LIMIT, no SQLi) — RESOLVED.** `repeated_request_signals.py:154-157` appends `" LIMIT ?"` with a parameterized `int(limit)` (no string interpolation). Detector passes `limit=_MATCH_CANDIDATE_LIMIT=500` (`repeated_request_detector.py:53,94`). Ordering `occurrence_count DESC, last_seen_at DESC` is applied before LIMIT, so the most-salient candidates survive the cap — match correctness preserved.

**W3 (oversized fail-closed) — RESOLVED.** `skill_safety_scanner.py:127-130` returns `safe=False` when `len(content) > _MAX_SCAN_LEN` (200k) before any regex. Boundary correct: `> ceiling` refused, `== ceiling` scanned (strict `>`). Direction is fail-closed. Confirmed by `test_oversized_content_fails_closed` + `test_at_ceiling_content_is_scanned_not_refused`.

**No new blocker/warning introduced.** Edits are minimal and localized; guards are additive (early-return / extra clause). Tests cover each fix including the negative bare-body-hash assertion.

**Verdict: PASS.**
