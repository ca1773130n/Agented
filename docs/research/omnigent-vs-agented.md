# Omnigent vs. Agented — competitive analysis & improvement plan

> Snapshot: **2026-06-30**. Source confidence: claims about what omnigent **has** are
> high (primary README / `deploy/README.md` / `POLICIES.md` / Releases API / source
> files, all 3-0 adversarially verified, several SHA-pinned). Claims that **"Agented
> leads because omnigent lacks X"** are *inferred from absence* in omnigent's public
> docs — "not evidenced," not "proven absent." Omnigent is ~18 days old and ships a
> minor every ~8 days, so re-verify before acting. Agented's side is from the internal
> description, not re-audited against the codebase here.

## TL;DR

[omnigent-ai/omnigent](https://github.com/omnigent-ai/omnigent) is a **Databricks-originated, Apache-2.0, Python open-source "meta-harness"** — the *exact same category* as Agented: a common orchestration layer above many coding harnesses (Claude Code, Codex, Cursor, OpenCode, Hermes, Pi, Goose, Copilot, Kiro, Kimi, Qwen, Antigravity + YAML "custom agents"). Created 2026-06-11, already **~5,437★ / 696 forks**, v0.3.0 on 2026-06-27. Same thesis as us — so this is about **execution, not concept**.

- **Omnigent is genuinely ahead on five operator-facing dimensions:** (1) a first-class **stackable policy/governance engine**, (2) **real-time multi-user collaboration**, (3) **sandboxing/deployment breadth**, (4) a **server/runner split** that keeps LLM keys out of the deployed image, (5) **frictionless distribution** (single `uv`/PyPI install + self-update + desktop app).
- **Agented is clearly ahead on depth:** the **unified loop layer** (LoopSpec + goal_loop_runner exit ladder, checkpoint/resume, carry-vs-reset, LLM-judge gate), **federated cross-project knowledge grounding** (Tesserae/CodeGraph), the **self-improvement life-harness**, the **competitive-intelligence pipeline**, **trigger-based delivery**, **GRD planning**, and **HarnessSync** — none of which surfaced in omnigent's docs.
- **Net:** omnigent is a **governance / collaboration / deployment exemplar to borrow from**; Agented owns the **autonomy / memory / self-improvement frontier**. Adopt their policy engine, OS-level harness sandboxing, and multi-user collaboration **without diluting** our loop/memory moat.

## 1. Omnigent capability map

- **Category & thesis:** "open-source meta-harness… common orchestration layer over Claude Code, Codex, Cursor, OpenCode, Hermes, Pi, and the agents you write yourself: swap or combine harnesses without rewriting." Three pillars: **Composition / Control / Collaboration**. One-line harness switch via the YAML `executor.harness` field.
- **Harness fleet (~12 executors):** `claude-sdk, claude-native, codex, codex-native, cursor, cursor-native, hermes, hermes-native, opencode, pi, pi-native, openai-agents`. v0.3.0 added 7 (Hermes, Copilot, OpenCode, Goose, Qwen Code, Kiro, Kimi) + promoted Antigravity to full SDK + native CLI.
- **Credentials (4 kinds):** API key / Subscription (Claude Pro/Max, ChatGPT via official CLIs) / Gateway (any OpenAI/Anthropic-compatible `base_url`: OpenRouter, LiteLLM, Ollama, vLLM, Azure) / Databricks. **Per-agent defaults coexist** (a Claude default and a Codex default at once).
- **Policy/governance engine (their standout):** `ALLOW/DENY/ASK` on every action, **stacked across 3 levels** (server admin / per-agent / per-session) with **stricter session rules checked first** and able to short-circuit. Builtins (real files — `cost.py` 42KB, `safety.py` 27KB): `cost_budget` (hard `max_cost_usd` + soft `ask_thresholds_usd`), `max_tool_calls_per_session`, `ask_on_os_tools` (approve before shell/file-write), `enforce_sandbox`, `deny_pii_in_llm_request`, `github_policy`, Google policies. `/v1/policies` REST API + custom-policy SDK.
- **Multi-agent orchestrators (declarative):** Polly (default `omni`) + Debby — plan, delegate to Claude Code/Codex/Pi sub-agents in **parallel git worktrees**, then **cross-vendor review** (each diff reviewed by a *different* vendor than wrote it). "Polly and Debby are just YAML configs" — a 17.6KB `config.yaml` + markdown skills, no imperative code.
- **Collaboration:** **Share** a live session by URL (watch + chat in real time); **co-drive** (`omnigent attach` — a teammate's messages execute on *your* machine); **fork** onto another machine (`omnigent run --fork`). Multi-user accounts + **OIDC SSO** (Google/GitHub/Okta/Microsoft).
- **Sandboxing/isolation:** **9 cloud sandbox providers** (Modal, Daytona, Islo, E2B, CoreWeave, Kubernetes, OpenShell, Boxlite, Databricks) + **OS sandbox per terminal** (bwrap mandatory on Linux, seatbelt macOS, Job Object Windows) behind an **L7 egress proxy**.
- **Deployment:** **server/runner split** — slim FastAPI/WS server (no harness SDKs, no tmux, **no LLM keys in the image**) + a Runner on the user's machine/cloud sandbox that dials in (`WS /v1/runner/tunnel`) and runs the loop locally. One shared image → **Render/Railway one-click (auto Postgres), Fly, HF Spaces, Modal, Cloudflare (D1+R2, scale-to-zero)**; **Postgres + SQLite both first-class** (same schema/migrations, `DATABASE_URL`).
- **Distribution:** `uv tool install omnigent` → `omnigent`/`omni` on PATH; **`omni upgrade` self-update** + startup out-of-date notice; auto-starts local server + web UI at `localhost:6767`; native **desktop app**.
- **Native-harness parity (v0.3.0, 7-harness subset):** compaction, cost/token tracking, resume, true fork-with-history, in-session model switching, tool-approval / AskQuestion web cards.

## 2. Feature-by-feature comparison

| Dimension | omnigent | Agented | Ahead |
|---|---|---|---|
| Agent-orchestration model | meta-harness, declarative YAML | meta-harness, hierarchical products→projects→teams→super-agents→agents→sessions | **TIE** |
| Multi-harness / backend breadth | ~12 executors | ~11 backends (ai-accounts) | **TIE** (slight omnigent) |
| Autonomy & loop control | per-harness native resume/compaction | unified LoopSpec + exit ladder, checkpoint/resume, carry-vs-reset, LLM-judge gate | **AGENTED** |
| HITL & safety gates | stackable ALLOW/DENY/ASK policy engine | RBAC + safety bots + per-iteration human-gate | **OMNIGENT** |
| Knowledge / memory / grounding | per-session (resume/fork/compaction) only | Tesserae federated semantic graph + CodeGraph MCP, recency-weighted | **AGENTED** |
| Observability / telemetry | cost/token tracking, AskQuestion cards | per-iteration records + budgets | **TIE** |
| Extensibility / plugins | declarative YAML agents/policies/MCP | code-defined; HarnessSync wiring | **OMNIGENT** (authoring ease) |
| Integrations | GitHub / Google policies | triggers: webhooks / GitHub / schedules / manual | **AGENTED** |
| UI / operator UX | multi-user live collab, desktop app, one-install | single-operator Vue console | **OMNIGENT** |
| Deployment / ops | 9 sandboxes + one-click targets + Postgres + key-isolated split | clone-and-run, raw SQLite | **OMNIGENT** |
| Self-improvement | none surfaced | life-harness + competitive-intel + GRD | **AGENTED** |

## 3. Lessons & prioritized improvement plan

### P1 — Stackable policy/governance engine *(high impact / moderate effort)* — their single clearest lead
Consolidate Agented's scattered controls (RBAC, `bot-security`/`bot-pr-review`, goal_loop_runner human-gate, exit-ladder budgets) into **one `ALLOW/DENY/ASK` policy layer** stacking across **server / team / session** scopes (stricter scope first), with builtins for cost caps (hard + soft thresholds), max tool calls, and approve-before-shell/file-write.
**Touches:** `app_litestar/middleware.py` (new policy middleware), `ExecutionService` (action interception), `goal_loop_runner.py` (human-gate hook), frontend `budgets.ts`/answer-eval surfaces. Anchor on **session** scope (per the standing session-not-bot rule), spanning project/team/workflow/trigger.

### P1 — OS-level harness sandboxing + egress control *(high impact / higher effort)* — real safety gap today
Wrap each `subprocess.Popen` harness in **bwrap (Linux) / seatbelt (macOS)** + an **L7 egress allowlist proxy**, generalizing `sandbox_eval.py` beyond deterministic checks to the *live* harness. Today harnesses run with autonomous file/shell/network access on the operator's host with only git-worktree isolation — the **competitive-intel auto-implement** and **life-harness autonomy** loops are the highest-risk consumers.
**Touches:** `ExecutionService` (subprocess launch), `sandbox_eval.py` (generalize), new egress-proxy. **Lower-effort interim:** an optional **cloud-sandbox runner (E2B/Modal)** for untrusted autonomous runs.

### P2 — Real-time multi-user collaboration *(high impact / high effort)*
**Share** a live SSE session by URL (read + chat), **co-drive** (a teammate's message executes against the operator's running session), **fork** a session; optional **OIDC SSO**. Agented already SSE-streams harness output, so **live-share is an incremental extension**; co-drive + OIDC are the larger lifts. Pairs naturally with P1 so shared sessions stay governed.
**Touches:** frontend SSE layer + Vue console (share/attach UI), `ExecutionService` session model (multi-attach), auth middleware (scoped share tokens), optional OIDC in ApiKey middleware + ai-accounts.

### P3 — Deployment & extensibility ergonomics *(medium impact / medium effort)*
(a) First-class **Postgres** alongside SQLite (same schema/migrations, `DATABASE_URL`) + a container image + one-click target; (b) a **single-install / self-update** distribution path; (c) **declarative YAML** agent/team/orchestrator definitions ("the YAML file is the agent") so teams/super-agents are authorable without code; (d) optional **server/runner key-isolation split** for hosted deploys.
**Touches:** `app/database.py` (Postgres adapter), packaging/deploy, teams/super-agents config layer, ai-accounts (runner-side key custody).

### Where Agented should **NOT** chase omnigent
Keep investing in the **moat** — the unified loop layer, Tesserae/CodeGraph grounding, life-harness, competitive-intel, GRD, and triggers have **no omnigent equivalent**. The goal is to **widen** the gap on autonomy/memory/self-improvement while **closing** it on governance/collaboration/deployment.

## Open questions to resolve before acting
1. Does omnigent have *any* equivalent to our iterate-until-converged exit ladder, or is autonomy strictly per-harness resume + orchestrator-YAML delegation? (Inspect the runner loop + Polly skills.)
2. Any persistent cross-session/cross-project memory, or purely per-session? (The dimension where our Tesserae/CodeGraph lead is asserted from absence.)
3. Any trigger/event/scheduled execution, or strictly interactive/CLI?
4. Real lift to OS-sandbox our `subprocess.Popen` harnesses without breaking their tool access — is a cloud-sandbox runner the faster path to the same guarantee?

## Sources (primary, verified)
- README — https://github.com/omnigent-ai/omnigent/blob/main/README.md
- Deploy docs — https://github.com/omnigent-ai/omnigent/blob/main/deploy/README.md
- Releases (v0.3.0) — https://github.com/omnigent-ai/omnigent/releases
- Built-in agents docs — https://omnigent.ai/docs/use/builtin-agents
- Databricks launch blog — https://www.databricks.com/blog/introducing-omnigent-meta-harness-combine-control-and-share-your-agents
