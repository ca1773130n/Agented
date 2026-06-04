# Hardening Audit — Harness Evolution & Autonomy Subsystem

Scope: `backend/app/services/harness_*.py` — the subsystem that mutates harness
configs, deploys plugins, and runs autonomous self-improvement loops.

Severity counts: **CRITICAL 2 · HIGH 5 · MEDIUM 6 · LOW 4**

Verification method: full read of all 14 files plus the called-into
`forge_materialization_service.py` (to confirm path-sanitization on the
evolver's apply path). Findings below are confirmed against the actual code,
not speculative.

---

## CRITICAL

### C1 — `apply_patch` is non-atomic and has NO rollback on partial failure
**File:** `harness_evolver.py:1023-1121` (`apply_patch`), called from
`run_evolution_round:1534` and `apply_dry_run_round:1648`.

**Problem:** `apply_patch` iterates `patch.entries` applying create/update/delete
operations against five different Forge repos sequentially, building a `journal`
as it goes. If entry *k* raises (e.g. `_create_hook` hits an `IntegrityError`,
or `_create_skill` fails an `OSError` mid-write), the exception propagates out of
`apply_patch`. The caller (`run_evolution_round:1603`, `apply_dry_run_round:1649`)
catches it and calls `evolution_repo.mark_failed(...)` — but the **first k-1
mutations are already committed** (rows created, files written, bindings added,
skills materialized to `.claude/skills/`) and are never reversed. The
`apply_journal` that `harness_evolution_rollback.reverse_apply_journal` needs is
also lost, because it is only persisted via `mark_applied` (line 1563/1660) which
is never reached on the failure path. Result: a half-applied harness mutation
with no journal → the round shows `failed` but the system state is corrupted and
**not** revertible through the supported rollback path.

**Fix:** Wrap the per-entry loop so a mid-loop failure reverses the
already-applied entries from the in-memory `journal` (call
`reverse_apply_journal(project_id, journal)`), OR persist the partial journal on
the failure path so `revert_round` can clean up. At minimum, on exception:
`evolution_repo.mark_failed(round_id, error_message=..., apply_journal_json=json.dumps(journal))`
and immediately attempt `reverse_apply_journal`. Wrap rule/hook/command DB writes
of a single round in one SQLite transaction where feasible.

### C2 — Eval gate fails OPEN, then autonomy auto-applies on the synthetic pass
**File:** `harness_evolver.py:1421-1439` (`_eval_gate` exception branch) +
`harness_autonomy.py:56,153`.

**Problem:** When `evaluate_patch` raises (LLM judge CLI missing, network/provider
outage, materialization error, any exception), the gate logs and stores a
**synthetic passing verdict** `EvalVerdict(passed=True, score=0.0, ...)` and
returns `None` (continue). On the autonomous path, `process_project_autonomy`
re-reads the round, sees `eval_verdict.passed == True`, and the `confidence`
gate is `score >= policy.confidence_threshold` — if a project ever sets
`confidence_threshold == 0.0`, a fail-open round with `score=0.0` **passes the
gate and auto-applies untested mutations** with no human in the loop. Even with a
nonzero threshold, the fail-open verdict pollutes the operator-facing
`awaiting_approval` state by claiming the patch "passed eval" when eval never ran.
This couples a transient infra failure (judge CLI unavailable) to unvetted
harness mutation — exactly the high-blast-radius path the eval gate exists to
guard.

**Fix:** Fail CLOSED for autonomy: on eval error, store `EvalVerdict(passed=False,
score=0.0, notes="eval bypassed due to error")` and short-circuit to a
non-auto-appliable state (e.g. `eval_failed` or a distinct `eval_errored` status).
If a human-review fail-open is desired for the *interactive* dry-run path, gate it
behind an explicit env flag and still mark the verdict `passed=False` so
`autonomous_apply_eligible`'s `eval_present` gate (line 56) rejects it.

---

## HIGH

### H1 — Path traversal in plugin/skill/team deploy file materialization
**File:** `harness_deploy_service.py:148,193`.

**Problem:** `_generate_harness_files` builds filesystem paths from
attacker-influenceable strings with no traversal guard:
- line 193: `skill_folder = os.path.join(skills_path, skill)` where `skill`
  comes straight from an agent's `skills` JSON array (line 181-187). A skill
  named `../../../etc/something` or `../../.github/workflows/x` escapes
  `.claude/skills/` and writes a `SKILL.md` into an arbitrary repo path that is
  then committed and pushed to the operator's GitHub repo (line 79-97).
- line 148: `safe_name` from a team name only does
  `.lower().replace(" ","-").replace(":","-")` — it does **not** strip `/` or
  `..`, so a team named `../../foo` also escapes `teams_path`.

Unlike the evolver (`_create_skill:1288`) and materialization service
(`_safe_name`), which both sanitize to `[alnum-_]`, this deploy path does not.

**Fix:** Sanitize every path segment with the same allowlist used elsewhere
(`"".join(c if c.isalnum() or c in "-_" else "-" for c in seg)`), reject empty/`.`
/`..` results, and assert the resolved path is inside the intended base via
`Path(folder).resolve().is_relative_to(base.resolve())`.

### H2 — No lock / serialization around concurrent evolution rounds for a project
**File:** `harness_evolver.py:1451-1610` (`run_evolution_round`),
`harness_autonomy.py:121-164`.

**Problem:** The only concurrency guard is the in-flight rate-limit check
(`_check_rate_limit:113`), which is a **read-then-act** race: two callers (e.g. a
scheduled job + a manual trigger, or two scheduler ticks) can both call
`list_for_project`, both see no in-flight round, and both `start_round` →
double-apply the same evolution against shared Forge state, doubling bindings and
racing the materialization git commit. `apply_dry_run_round` similarly checks
`status == awaiting_approval` (line 1626) then applies, with no row lock between
check and `mark_applied` — two operators clicking "approve" both pass the check
and apply twice. SQLite gives statement-level atomicity but nothing serializes
the multi-statement round.

**Fix:** Add an advisory lock per `project_id` (a `harness_evolution_locks` table
with a unique constraint, or `SELECT ... FOR UPDATE`-style guarded status
transition) so `start_round` and the awaiting_approval→applied transition are
compare-and-swap. `mark_applied` should be conditional on current status still
being the expected pre-state and return whether it won.

### H3 — Scratch workspace leaked on the success path (default keeps on failure too)
**File:** `harness_evolver.py:1457,1476-1482,1594-1595`.

**Problem:** `run_evolution_round` creates a scratch dir via `tempfile.mkdtemp`
(line 1477) under `/tmp`. It is only removed at line 1594 **when
`keep_scratch_on_failure=False`** — but that flag defaults to `True` (line 1457),
and even when False, cleanup is on the *success* branch only. On every failure,
eval-fail, dry-run (`awaiting_approval` returns at 1528), validation-fail (1511),
and the exception branch (1603), the scratch dir — containing the full Forge
config dump, trajectories, takeaways, and Tesserae context — is **never deleted**.
Each round leaks a directory; over time `/tmp` fills and sensitive project
internals accumulate world-readable under default `/tmp` perms. The misnamed flag
(`keep_scratch_on_failure`) actually controls success-path cleanup.

**Fix:** Use a `try/finally` (or `tempfile.TemporaryDirectory`) so the scratch
dir is removed on every exit path unless an explicit debug flag is set; only
preserve it on failure when `keep_scratch_on_failure=True`. Rename the flag to
reflect actual semantics. Set restrictive dir perms (0700).

### H4 — Plugin install ignores exit code → silent broken deploy
**File:** `harness_plugin_installer.py:49-55`.

**Problem:** `ensure_plugins_installed` runs `claude plugin install <name>`
(line 49) but never inspects `result.returncode`. A failed install (network,
auth, marketplace resolution failure) is completely silent — the function returns
normally and the caller believes the harness is fully provisioned. The marketplace
`add` (line 30) at least logs a warning; the actual install does not even log.
Plugin names come from a hardcoded constant here (`BUNDLE_PLUGINS`) so it's not an
injection vector, but the silent failure masks a broken harness environment.

**Fix:** Capture and check `returncode`; log at warning/error with `stderr` on
non-zero, and surface a structured result (installed/failed lists) to the caller
so the operator sees partial-provisioning.

### H5 — Skill create/delete writes to project filesystem with no path containment assert
**File:** `harness_evolver.py:1283-1346` (`_create_skill`, `_delete_skill`).

**Problem:** `_create_skill` sanitizes the skill name to `[alnum-_]` (line 1288)
which prevents traversal, BUT `_project_root` (line 1261) returns whatever
`local_path`/`clone_path` is stored for the project with no validation that it is
a real, intended directory, and `skill_dir.mkdir(parents=True)` (line 1290) will
create arbitrary parent directories. `_delete_skill` (line 1333-1346) does
`skill_md.unlink` and `parent.rmdir` based on a stored `skill_path` from the DB —
if that path was ever set to something outside the skills tree (e.g. via the
loader importing a crafted SKILL.md, or a corrupted row), the delete operates
outside the skills dir. The `parent.name != "skills"` guard (line 1342) is a weak
heuristic, not a containment check.

**Fix:** Resolve `skill_dir`/`skill_md` and assert `is_relative_to` the project's
`.claude/skills/` root before any `mkdir`/`write`/`unlink`/`rmdir`. Validate
`local_path` is an existing directory the service is allowed to write to.

---

## MEDIUM

### M1 — Codex runs with `--sandbox workspace-write` but writes are parsed back into live config
**File:** `harness_evolver.py:820-827,830-878`, `parse_patch:886-966`.

**Problem:** The scratch workspace given to `codex exec` contains the project's
real Forge primitive payloads (rule/hook/command **content**, mcp_server
`command`/`args`/`env_json`). Codex is an LLM agent with `--sandbox
workspace-write` and `--skip-git-repo-check`; whatever JSON it writes back is
parsed (`parse_patch`) and—on the autonomous path—applied **without any human
inspecting the hook shell `content` or mcp_server `command`**. `validate_patch`
(line 974) checks structural presence (event in allowed set, content non-empty)
but never inspects the *content* of a hook shell command or an mcp_server
`command`/`args` for danger. An evolution round can therefore introduce a
PreToolUse hook whose `content` is an arbitrary shell command, or an mcp_server
that launches an arbitrary binary, which then runs in every future session.

**Fix:** Add content-level validation/allowlisting for hook `content` and
mcp_server `command`/`args` (deny obviously dangerous patterns, or require these
specific kinds to always go through human approval — exclude `hook`/`mcp_server`
from `policy.allowed_kinds` defaults in autonomy). The blast-radius and
allowed_kinds gates exist (`harness_autonomy.py:72-87`) — ensure the default
policy excludes shell-bearing kinds from auto-apply.

### M2 — `gather_inputs` snapshot window filtering is O(n) python after over-fetch
**File:** `harness_evolver.py:413-418`.

**Problem:** `snapshots_repo.list_for_project(project_id, limit=limit*2)` fetches
then filters `since`/`until` in Python (lines 414-417) and slices to `limit`.
With a high `limit` this over-fetches; more importantly the `since`/`until` filter
is applied *after* the DB limit, so a project with many recent snapshots outside
the window can silently yield fewer-than-`limit` in-window trajectories (a
correctness/observability gap, not a crash). Low risk but masks data.

**Fix:** Push `since`/`until` into the repo query (the impact module already
supports `before_ts`/`after_ts` in `snapshots_repo.list_for_project`).

### M3 — `_git_revert` runs `git revert --abort` unconditionally, may discard unrelated in-progress merge
**File:** `harness_evolution_rollback.py:142-150`.

**Problem:** Before reverting, it runs `git revert --abort` "best-effort" to clear
a prior failed revert. If the operator happens to have an unrelated in-progress
revert/merge in that working tree (these projects use real `local_path` working
trees), this silently aborts it. The subsequent `git revert --no-edit <sha>` is
also not guaranteed to be the only change (no clean-tree check), so a revert can
conflict with uncommitted local edits and fail mid-way, leaving a half-reverted
tree while the DB journal reversal already succeeded (the function returns failed
but DB is already changed — partial state, line 195-216).

**Fix:** Check `git status --porcelain` for a clean tree before reverting; only
`--abort` if a revert is actually in progress (`.git/REVERT_HEAD` exists). Surface
that DB was reversed but git was not (it does set `revert_error`, which is good —
but document the divergence).

### M4 — `reverse_apply_journal` delete-reversal can silently skip restoration
**File:** `harness_evolution_rollback.py:76-87`.

**Problem:** On reversing a `delete`, it calls `_already_restored` (line 80) and
skips re-creating if a same-named asset exists. But `_already_restored` swallows
all exceptions returning `False` (line 46-48) AND for `create` reversal it deletes
by `asset_id` without verifying the asset is the one this round created — if a
later round re-used/re-created the same name with a new id, the conflict check
(`_later_applied_conflicts`) is the only guard and it's skipped under `force=True`.
A forced revert can therefore delete an asset a *later* round created. Counted as
medium because `force` is operator-initiated.

**Fix:** When reversing a `create`, verify the current asset still matches the
before-image identity before deleting; don't rely solely on the conflict check
being run.

### M5 — Tesserae context build fans out one LLM call per takeaway with a 5-cap but no global budget
**File:** `harness_evolver.py:703-766` + `harness_kg_signals.py:121-165`.

**Problem:** `_build_tesserae_context_md` issues up to 5 `ask_tesserae` shell-outs
(line 753) and `gather_kg_signals` issues 3 more, every round. Each is a
subprocess LLM call with its own cost. There is a per-round cap but **no
cross-round budget guard and no aggregate cost ceiling** — combined with the eval
judge (up to 8 replay samples, `_replay_samples_from_inputs:1396`) and the Codex
exec, a single evolution round can spend a large, unbounded-in-aggregate amount of
LLM budget. Autonomous mode (`process_project_autonomy`) iterates up to 50 rounds
per project per invocation (line 129) with only a daily `rate_limit_per_day` count
gate, not a token/cost budget.

**Fix:** Add an explicit per-round and per-day LLM-cost/budget guard
(env-configurable), checked before fan-out, in addition to the existing count
rate-limit.

### M6 — `_run_codex_in_workspace` does not bound output capture
**File:** `harness_evolver.py:855-862`.

**Problem:** `subprocess.run(..., capture_output=True)` buffers all of Codex's
stdout/stderr in memory with no size cap. A misbehaving/runaway Codex producing
huge output could exhaust memory in the gunicorn worker (workers=1). The timeout
(600s) bounds time but not output volume.

**Fix:** Stream with a bounded buffer, or cap via reading from pipes with a max-
bytes guard.

---

## LOW

### L1 — `_kill_switch_on` checks env at decision time only
**File:** `harness_autonomy.py:24-25`. The kill switch (`AGENTED_AUTONOMY=0`) is
read per-decision, which is fine, but there is no kill switch for an *in-progress*
`run_evolution_round`/Codex subprocess — flipping the env mid-round does not abort
a running round. Fix: check the kill switch before `apply_patch` as well, and
support aborting in-flight rounds.

### L2 — Loader/deploy `Exception` swallowing returns HTTP 200 with `exists:False`
**File:** `harness_loader_service.py:95-100`. On any clone/IO error
`check_harness_exists` returns `HTTPStatus.OK` with `exists:False` and the raw
exception string — masking real failures as "no harness" and leaking error
internals to the client. Fix: distinguish "not found" from "error", use 5xx for
genuine failures.

### L3 — Loader imports agents/hooks/commands from untrusted GitHub repo content
**File:** `harness_loader_service.py:190-462`. Hook `content` and command
`content` are imported verbatim from a cloned repo's `.claude/` files into the DB
(`create_hook` line 358, `create_command` line 391) with only event-name
validation — the shell `content` of a hook is trusted. A malicious repo can seed a
PreToolUse hook that runs arbitrary shell once bound. Fix: treat
GitHub-loaded hook/command content as untrusted; require review before binding.

### L4 — `materialize/commit` failure on apply path is logged but masked as success
**File:** `harness_evolver.py:1545-1561`. If `materialize_primitives` or
`commit_materialization` raises, it's caught and logged, then the round is still
`mark_applied` (line 1563) with `mat_json=None, commit_sha=None`. The DB says
"applied" but the `.claude/` files were never written/committed — the running
harness does not actually have the new primitives until the next materialization.
This is intentional ("must not unwind the DB apply") but the divergence is silent.
Fix: record a `materialization_failed` flag on the round so the operator/UI can
see the DB and filesystem diverged.

---

## Notable GOOD practices (for contrast / do not regress)

- `harness_autonomy.autonomous_apply_eligible` is a clean, well-gated multi-gate
  decision (kill switch, eval-present, confidence, blast-radius, allowed-kinds,
  block-deletes, cooldown, daily rate-limit) — the gating model itself is solid.
  The weakness is what feeds it (C2 fail-open verdict, M1 unvalidated content).
- `harness_evolver._check_rate_limit` has a thoughtful orphan-reaper for stale
  in-flight rounds (line 145-184).
- `harness_takeaway_extractor._slugify` (line 375) and
  `forge_materialization_service._safe_name` (line 69) correctly sanitize to
  `[alnum-_]`, preventing traversal — the deploy service (H1) is the outlier that
  forgot to.
- `harness_snapshot_service` and `harness_failure_annotator` are read-only /
  capture-only and never raise into the spawn path — appropriate.
- Apply journal + `reverse_apply_journal` + git-revert give a real rollback path
  for *fully-applied* rounds; the gap (C1) is the partial-apply case.
