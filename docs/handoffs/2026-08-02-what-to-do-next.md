# Handoff — 2026-08-02

State: `main` at `55276c3355`. No unmerged branches, no stashes, clean tree,
backend suite green (5469 passed, 0 failed).

Ten PRs merged (#373–#382). The CLI is done and tested, the super-agent memory
loop runs end to end, and the backend suite has no tolerated failures left.

---

## Start here: the one thing that is still unproven

A distill that actually spends money has never happened.

The automatic path fires correctly (verified 2026-08-01, log in `CLAUDE.md`), but
it costs nothing every time, because there is nothing to summarise. The free dry
run reports `clusters=0 estimated_llm_calls=0 scope=1`. The agent
`claude:unknown:sa-apoc` does have scope; one session with 8 decisions just does
not form a cluster.

So everything downstream of that is still theory: the `≥n` partial-cost path, the
1800 s timeout and its `killpg` reaping, and whether the ≤60-call pricing gate is
calibrated to anything real.

### What will NOT fix it

Importing more harness sessions. I tried. `tesserae sessions discover --import`
pulled 377 real Claude Code / Codex sessions for GetResearchDone, and all 377
carry `agent_label = "Codex"`. The distill's scope is `known_agent_keys`, read
from `.tesserae/agents/registry.json`, which `sync_agent_registry` derives from
Agented's `super_agents` table. That table currently holds exactly one agent,
matching label `sa-apoc`. None of the 377 can reach the distiller.

Widening the registry match rule to sweep those sessions under "Apoc" would be
fabrication, since the runbook would then claim an agent did work it never did.
It also would not survive the next compile, which regenerates the registry from
the DB.

The blocker was never volume. It is attribution.

### What will

Real super-agent sessions on an opted-in project, each carrying a `project_id`.
Run super-agents against GetResearchDone through the platform, let the sessions
complete, then let the automatic path do its thing. The preconditions are already
in place:

- `projects.tesserae_distill_enabled = 1` for GetResearchDone
- the graph is built (5808 nodes), which it was not until 2026-08-01
- `sync_agent_registry` writes a flat registry, avoiding the
  `manager_children_unbuilt` trap that makes hierarchical registries unpriceable
- session→project attribution is fixed (see below)

Watch `last_auto_distill` on `/admin/system/memory/tesserae/projects`. The first
real cost number should show up there.

---

## Before you touch super-agent sessions, know this

`_fix_stale_session` used to delete a stale session and recreate it without the
project id. The Tesserae export hook opens with `if not project_id: return`, so
agent memory for that project silently never populated again. Fixed in #377, and
it explains why only 1 of 5 session rows is attributed.

The remaining 4 (`sa-system`, `project_id IS NULL`) are correct.
`_run_tier2_investigation` is a system-level error investigation with no project
in scope, and `system_errors` has no project column. I verified that rather than
assuming it. Do not "fix" them.

---

## Open, in rough priority order

### 1. Upstream bug filed, awaiting a decision — [Tesserae#104](https://github.com/ca1773130n/Tesserae/issues/104)

`tesserae sessions discover --import` replaces the harness-session store, while
`tesserae sessions import <path>` merges it. A non-empty discovery therefore
prunes records it structurally cannot see, meaning anything written by an
external producer. Agented's session export is exactly that.

It cost us the only attributed session in the store. Re-running the export
restored it, and the manifest is now 378 with `sa-apoc` present. The loss is
silent: the run prints `Imported harness sessions: 377` while the store shrank.

The mechanism is `replace=bool(sessions)` at `cli.py:1973` and `cli.py:2225`,
against an API that defaults to merge. Present in 0.28.2 and 0.28.5.

Action: if the maintainer picks a direction, send the PR. I offered.
Meanwhile: never run `tesserae sessions discover --import` on a project whose
store has externally-imported sessions without re-running Agented's export
afterwards.

### 2. ~~`ag qa` has never been run end to end~~ — DONE, see PR #384

It has now, against a copy of the local DB with an empty sidecar store. It found
two bugs: its own crash reporting itself as "HIGH findings" instead of 3, and a
`GET /admin/system/memory/graph/map` that had 500'd on every call since it was
wired (`scope` is a Litestar reserved kwarg). Both fixed. The rest of the run's
8 critical / 85 high was self-inflicted: 7 criticals are the offline mutator's
own doing, 64 highs are one rate-limited button, and the 7 "unreached" routes
all render fine on a fresh context.

One thing to know before the next run: the crashes fed `error_capture`, which
spawned a real `claude -p … --dangerously-skip-permissions` subprocess that
edited backend source mid-run.

**There is no way to turn that off.** `capture_error` calls `trigger_autofix`
unconditionally (`error_capture.py:93`), and no env var or setting gates it —
an earlier version of this file told you to set `AGENTED_AUTOFIX_*`, which does
not exist and never did. Which backend it spends on is now configurable and
defaults to codex (#384); whether it runs at all is not. So a QA run against a
build that 500s will spend tokens and write to your tree, and the only lever is
not provoking the errors.

The original note follows.


`cli/commands/qa.ts` wraps mischief for random-click QA and is tested at the unit
level, but has never been pointed at the running app.
`frontend/mischief.config.mjs` declares 24 routes read from the router, with
`requiresAuth` on the 22 gated ones.

Exit code 3 means *unverified* and is deliberately passed through rather than
flattened into pass/fail. Do not "fix" that into a 0 or 1.

Needs `just deploy` up first.

### 3. Decide whether to compile the 377 imported sessions

They are in the store and they are real. Compiling would put them in the project
graph, which is what Tesserae is for and improves retrieval regardless of
distill. It is a ~300-session LLM extraction, so it is real spend, and it does
not advance the billing-distill goal (see above). I stopped rather than spend on
it unilaterally.

### 4. Postgres is still experimental

Unchanged from `CLAUDE.md`, listed here so it does not get forgotten: full-text
search degrades to `ILIKE`, some SQLite-only maintenance paths are skipped, and
not every code path is PG-exercised. SQLite remains the supported default.

---

## Things that will mislead you if nobody says them

The backend suite does not hang. It takes 13–17 minutes. `CLAUDE.md` used to
prescribe killing it at 12 minutes, which killed it every time at whatever
percentage it had reached, and that kill was then read as the hang. The procedure
manufactured the symptom it described. Run it and wait. Background it so a
harness timeout cannot cut it, and never pipe it through `tail`, which buffers
and makes a live run look dead.

There is no tolerated-failure list any more, and there should not be one again.
All 20 were triaged in #382. One was a real bug, a PATH probe added in June
silently outranking the explicit `CLAUDE_PLUGIN_ROOT` override, and its three
tests had been correct and red for seven weeks.

Two failure shapes are about the developer's machine, not the code. A shell
exporting `AGENTED_API_KEY` (this one's `~/.zshrc` does) makes "no auth
configured" false. And `config_status` / `graph_status` cache to
`~/.cache/agented/tesserae`, so a stubbed test could assert against your real
cache. That is why four tests looked flaky: the failures tracked a 60-second TTL,
not code. Both are neutralised in `tests/conftest.py`, but they are the shapes to
suspect when a test fails only for you.

A no-op is not a pass. `tesserae compile --changed-only` reported
`processed=0 skipped=316` against a 302-node graph for who knows how long. The
manifest claimed everything was current while the graph was never built. Check
`processed > 0` before believing a compile did anything.

---

## How to verify a change

```bash
just build                                   # vue-tsc + vite
cd backend && uv run pytest                  # 5469 passed, 0 failed (~14 min)
cd frontend && npm run test:run              # 1727 passed, 0 failed
cd cli && node --test --experimental-strip-types test/*.test.ts   # 57 passed
cd backend && uv run pytest tests/test_cli_contract.py            # 9 passed
```

`test_cli_contract.py` is the independent oracle for the CLI. It validates all
784 alias paths against the server's real route table, and it caught two classes
of wrong command that the CLI's own coverage test passed, because that test
shares normalisation logic with the generator and therefore agrees with its bugs.
If you change `frontend/src/services/api/`, run `just cli-gen` and commit the
result.

---

## One note on method

The recurring failure this session was not bugs. It was work that looked finished
but was not, protected by a label that discouraged looking: merged PRs whose
review fixes never landed, stashes nobody opened in five months, a memory loop
reporting success against an empty graph, a documented hang that was really a
watchdog, twenty "known" failures that turned out to be six real defects.

I reproduced that same failure mode three times myself: a duplicate route for
work that already existed, a boolean fix that wrote `true` into string fields,
and twice a test that was green for the wrong reason. Every one was caught by
review rather than by me, which is the argument for running the review passes.
