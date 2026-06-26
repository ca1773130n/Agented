# Code as Agent Harness — Apply to Agented

Source paradigm: arXiv:2605.18747 (Code as Agent Harness). Executable code is the
action space; the subprocess+sandbox is the harness; execution feedback (compiler
errors, test pass/fail, exceptions, assertions) is the objective oracle and
convergence signal.

## 1. Bottom line

Agented is **already a CodeAct system**. The harness action is executable code (a
CLI agent runs Bash/code in a workspace), `ExecutionService` `Popen`-streams it,
`goal_loop_runner` feeds captured output back as the next observation, and
`sandbox_eval` runs code-actions returning `rc/stdout/stderr` as verdicts. The
paper's three layers — executable interface, sandboxed feedback loop,
multi-agent coordination over shared artifacts — are mostly **infrastructure that
already exists**. The survey's framing is validation, not a build list.

Three changes are genuinely worth doing, all **prompt-assembly / one-field edits
reusing existing plumbing** — no new services, schemas, or executors:

1. **Self-debug: feed the captured failing trace back into regeneration.** The
   trace is captured (`verdict.stdout`) and persisted (`goal_loop_iterations.judge_stdout`)
   but **never shown to the regenerating agent** — it re-attempts blind. (high value, small)
2. **Oracle-arbitrated team hand-offs.** The generator/critic topology exits on an
   AGENT OPINION (`"APPROVED" in critic_output`) — the exact anti-pattern the
   papers replace. The objective oracle (`run_isolated_check`) exists but isn't
   wired into any topology. (high value, small)
3. **Code-graph context into reset/resume seed.** The 47MB `.codegraph.db` is
   operator-only; reset children re-grep from zero. (medium value, medium)

Everything else CodeAct/RLEF/Voyager/MetaGPT prescribes is **already shipped**.

## 2. Ranked recommendations

| # | Title | Reuses | Minimal change | Effort | Value |
|---|---|---|---|---|---|
| 1 | Feed failing trace into self-debug regeneration | `goal_judge._run_deterministic` (`verdict.stdout`), `sandbox_eval.IsolatedResult`, `goal_loop_iterations.judge_stdout`, `_continue_prompt`/`_build_resume_context` | Fold `r.stderr` tail into `verdict.stdout`; add a `trace_block` to `_continue_prompt` and add `judge_stdout` to the resume SELECT, gated behind the ouroboros flag | small | **high** |
| 2 | Oracle-gated generator/critic hand-off | `topology_strategies.execute_generator_critic`, `sandbox_eval.run_isolated_check`, shared `working_directory`, `TopologyConfig` | Add optional `check_cmd`; replace `"APPROVED" in critic_output` with `run_isolated_check(check_cmd, working_directory)`, feed failing stdout/stderr back as next generator msg | small | **high** |
| 3 | Code-graph block in reset/resume seed | `_build_resume_context`, recent `goal_loop_iterations`, `.codegraph/codegraph.db` (read-only) | Add `_code_graph_context(cwd)` querying the existing index for top-N changed files → symbols + callers/callees (~30 lines), append near dead-ends, flag-guarded | medium | **medium** |
| 4 | Task-similarity skill retrieval (Voyager compose-step) | `embedding_service` (+ `_text_similarity` fallback from `discovery_service`), `user_skills`, execution_service skill-path injection | `select_skills_for_task(project_id, task_text, k=3)`; rank `user_skills` by embedding/token overlap, inject top-k paths at the existing skill-injection point | medium | medium |
| 5 | Literal last-turn stdout/stderr as next observation | `goal_loop_runner._continue_prompt`/`_send_continue`, `verdict.stdout`, `dead_ends_block` pattern | Thread an optional `observation_block` (last check's stdout/stderr) into the continue prompt so carry/reset is lossless | small | low |
| 6 | Self-verify guard: check_cmd vetoes LLM "met" | `goal_judge.judge` precedence, `_met_terminates`/`LoopExit`, `goal_check_disagreement` event | 1-veto guard so a configured `check_cmd` is authoritative over an llm_judge "met"; optionally surface the existing divergence event as a UI badge | trivial | low |
| 7 | Per-iteration rollback-on-gate-fail | `loop_progress.head_commit`, worktree cwd, `harness_evolution_rollback._git_revert` safety pattern | Opt-in `iteration_rollback` flag (default off): `git reset --hard <start_sha>` + `git clean -fd` on gate FAIL before next iteration | small | low |

## 3. Already covered — do not rebuild

- **CodeAct unified action space** — `ExecutionService`/`TeamExecutionService` +
  `command_builder.build` + `goal_loop_runner` act→observe loop; the action is
  already executable code, not a JSON tool registry. (Also a 2nd interpreter:
  `ctx_execute`.)
- **Sandboxed execution with governance** — `sandbox_eval.py`
  (snapshot copytree + scrubbed-env allowlist + own process group + SIGKILL-group
  on timeout + escaping-symlink neutralization) is a 1:1 match.
  `permission_prompt_service` = per-call capability governance (HITL).
  `harness_evolution_rollback.revert_round` = transactional/git-reversible rollback.
- **Oracle-precedence exit ladder** — `goal_judge_service.judge` (metric_spec >
  deterministic check_cmd > llm_judge); `_met_terminates` + exit ladder; ReVeal-style
  cross-verify (`_maybe_stale_check` → `goal_check_disagreement`); Ouroboros
  hypothesis-scoring + dead-end registry.
- **Memory as program state** — `_build_resume_context` rebuilds from SQLite
  verdicts + dead-ends (not transcript); `loop_progress.head_commit/made_progress`
  treats git HEAD as the stateful world; `_RunnerState` + `goal_loop_iterations`.
- **Voyager accretion half** — `harness_takeaway_extractor.on_session_complete`
  (every session) → `skill_sleep_service.SkillSleepGate` blind-judge strict-improvement
  gate → `harness_evolver._create_skill` writes `SKILL.md` + `user_skills`.
- **Multi-agent infra** — `topology_strategies` (generator/critic, coordinator,
  hierarchical, sequential, parallel, HITL); shared `working_directory`;
  `agent_message_bus_service`.
- **RLEF training loop** — out of scope: Agented drives external CLI harnesses via
  subprocess; there is no policy to fine-tune.

## 4. Per-recommendation detail

**1. Feed failing trace into self-debug regeneration (high / small).** The loop is
structurally complete but the regenerating agent never sees the trace: in the carry
path `_continue_prompt` gets only `verdict.reason` ("check exited 1"), and the reset
path `_build_resume_context` drops `judge_stdout` entirely. Two edits: in
`goal_judge_service._run_deterministic` (~lines 287-299) fold a tail of `r.stderr`
into `verdict.stdout` so pure-stderr tracebacks survive; then thread `verdict.stdout`
(~2KB) as a `trace_block` into `_continue_prompt` and add `judge_stdout` to the
`_build_resume_context` SELECT. Reuses already-captured, already-persisted state;
gate behind the ouroboros flag so legacy plain-continue is unchanged.

**2. Oracle-gated generator/critic hand-off (high / small).** `execute_generator_critic`
in `topology_strategies.py` exits on `"APPROVED" in critic_output.upper()` — an agent
opinion deciding convergence, the anti-pattern MetaGPT/AgentCoder replace. Add one
optional `check_cmd` field (surface in `TopologyConfig`, which is JSON — no migration);
when set, run `run_isolated_check(check_cmd, working_directory)` after each generator
iteration against the already-shared workspace, break on rc 0, else feed
`result.stdout/stderr` back as the next generator message instead of the critic's prose.
~15 lines, reuses the sandbox oracle and shared cwd verbatim.

**3. Code-graph block in reset/resume seed (medium / medium).** `.codegraph/codegraph.db`
is operator-only (zero references in `backend/app`); a `context_policy=reset` child
re-greps the repo from zero. Add `_code_graph_context(cwd)` that opens the existing
index read-only and pulls a compact repo-map (top-N files from recent
`goal_loop_iterations` → defined symbols + immediate callers/callees, ~30 lines),
appended in `_build_resume_context` near the dead-ends block, flag-guarded so
no-index deployments no-op. YAGNI fallback: seed with `git diff --name-only` of files
changed this loop.

**4. Task-similarity skill retrieval (medium / medium).** Voyager's accretion is fully
built; only the retrieve-and-compose step is missing — selection today is static
(`harness_loader_service.matched_skills`) or manual (`skill_sets`). Add
`select_skills_for_task(project_id, task_text, k=3)` ranking `user_skills` (name +
description + SKILL.md head) via `embedding_service` exactly as
`discovery_service._resolve_readme_mode` does, with the same `_text_similarity`
stdlib fallback, and inject the top-k at the existing skill-path point in
`execution_service.py` (~line 570). No new tables or gate.

**5. Literal last-turn stdout/stderr as next observation (low / small).** Today
`_continue_prompt` feeds the gate's `reason`, not the agent's last-turn raw output;
on `context_policy=reset` that observation is lost. Add an optional `observation_block`
through `_send_continue` carrying the just-run check's stdout/stderr (already on hand as
`verdict.stdout`), mirroring the `dead_ends_block` injection. Largely subsumed by #1.

**6. Self-verify guard: check_cmd vetoes LLM "met" (low / trivial).** When `check_cmd`
is present it's already the sole judge, so this only matters for mixed gates: add a
1-veto guard in `_met_terminates`/`LoopExit` so a configured `check_cmd` is
authoritative over any llm_judge "met". Optionally surface the already-broadcast
`goal_check_disagreement` event as a UI badge (frontend-only). Net: ~0 new services.

**7. Per-iteration rollback-on-gate-fail (low / small).** A loop iteration is not a
transaction — on gate FAIL the failed diff is left in place and can poison the next
iteration. Opt-in `iteration_rollback` flag (default off, like the `sandbox:
isolated|inherit` switch): capture `loop_progress.head_commit(cwd)` before the body,
and on FAIL in a worktree run `git reset --hard <sha>` + `git clean -fd`, mirroring
the dirty-tree/own-cwd guards in `harness_evolution_rollback._git_revert`. If
carry-forward-on-fail is intentional for Ralph's deep iteration, skip it — default-off
makes it a non-regression.
