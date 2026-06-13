<div align="center">

# Agented

**A harness-engineering meta-layer for AI coding agents.**

Orchestrate Claude Code, Codex, and Gemini CLI into end-to-end, autonomous
product development — from one operator console, with provenance and
auditability built in.

[Architecture](docs/self-improving-harness-architecture.md) · [Tutorial](docs/self-improving-harness-tutorial.md) · [Security](docs/SECURITY.md) · [Deploy](docs/deploy/RUNBOOK.md) · [한국어](docs/ko/index.md) · [日本語](docs/ja/index.md) · [中文](docs/zh/index.md)

</div>

---

Agented is the **control plane on top of AI coding harnesses**. It coordinates
**products → projects → teams → agents**, drives the underlying CLIs as live
subprocesses, and streams their work back to you in real time. On top of that
sits a **self-improving harness**: every action an agent takes is checkpointed,
attributed to its source, budget-governed, and verifiable — provenance and
auditability as first-class concerns, not afterthoughts.

## Quickstart

```bash
# Fresh machine — auto-installs just, uv, and Node.js, then all deps (safe to re-run)
bash scripts/setup.sh

# Already have the prerequisites?
just setup        # install all dependencies
just dev-all      # backend :20000 + sidecar :20001 + frontend :3000
```

Open the console at **http://localhost:3000**. Interactive API docs (Swagger UI)
live at **http://localhost:20000/schema**. Run pieces individually with
`just dev-backend`, `just dev-frontend`, `just dev-ai-accounts`.

> **First run:** the **first** account to register becomes admin. Set
> `AGENTED_DISABLE_SIGNUP=1` once you've registered — always before exposing the
> instance to an untrusted network.

## What's inside

**🎛 Multi-harness orchestration** — Drive Claude Code, Codex CLI, and Gemini CLI
as subprocesses and stream their output over SSE. Work is delivered by
**triggers**: webhooks, GitHub events, schedules, or a manual run.

**🗂 Organization model** — Products, projects, teams, agents, and predefined
bots, wired together through one dashboard. Per-project context, accounts, and
**Forge primitives** (plugins, skills, hooks, commands, rules) compose into each
run.

**🔁 The self-improving harness** — Durable per-run state with incremental
checkpoints (crash recovery + `--resume`), an append-only **evidence ledger** of
every tool call, **verification records** that gate side effects, **live per-run
budget discipline** (soft warn → hard stop), and goal-loop re-entry. Provenance,
auditability, and rollback are designed in. → [Architecture](docs/self-improving-harness-architecture.md)

**💬 Dependable answers (agentic RAG)** — Leader-chat answers run through a
planner → multi-source fanout → sufficient-context loop → grounded answer, with
provenance-tagged extracted facts and a blind LLM-as-judge usefulness eval.
Injection is gated on retrieval relevance **and** per-project corpus health, so
the pipeline only runs where it measurably helps. → [Research report](docs/harness-1-integration.md)

**🔐 Identity sidecar** — `ai-accounts` owns AI-backend accounts, credentials, and
login flows on `:20001`. → [Integration](docs/ai-accounts/AGENTED-INTEGRATION.md)

**🌍 Operator console** — Vue 3 dashboard, dark theme, full i18n
(English · 한국어 · 日本語 · 中文).

## Architecture

| Layer | Stack | Port |
|---|---|---|
| **Backend** | Litestar (gunicorn / UvicornWorker), raw SQLite, subprocess + SSE | `:20000` |
| **Frontend** | Vue 3 + TypeScript operator console | `:3000` |
| **Sidecar** | `ai-accounts` — AI-backend identity & credentials | `:20001` |
| **Memory** | Tesserae typed knowledge graph + CodeGraph symbol index | — |

## Configuration

| Variable | Description | Default |
|---|---|---|
| `AGENTED_DISABLE_SIGNUP` | Close open self-registration (set after the first admin) | unset (open) |
| `AGENTED_DB_PATH` | SQLite database path | `backend/agented.db` |
| `AI_ACCOUNTS_API_KEY` | Token for the `ai-accounts` sidecar | reuse admin key |
| `AGENTED_RAG_MIN_CORPUS` | Min durable corpus items before leader-chat RAG runs | `8` |

Full environment reference and conventions live in [CLAUDE.md](CLAUDE.md).

## Verify

All three gates should pass before shipping:

```bash
just build                       # vue-tsc type-check + vite build
cd backend && uv run pytest      # backend suite
cd frontend && npm run test:run  # frontend suite
```

## Documentation

| Topic | Link |
|---|---|
| Self-improving harness — architecture | [docs/self-improving-harness-architecture.md](docs/self-improving-harness-architecture.md) |
| Self-improving harness — tutorial | [docs/self-improving-harness-tutorial.md](docs/self-improving-harness-tutorial.md) |
| Harness-1 integration (research) | [docs/harness-1-integration.md](docs/harness-1-integration.md) |
| Security | [docs/SECURITY.md](docs/SECURITY.md) |
| Deploy — runbook · backup · secrets | [runbook](docs/deploy/RUNBOOK.md) · [backup](docs/deploy/BACKUP.md) · [secrets](docs/deploy/SECRETS.md) |
| ai-accounts sidecar | [docs/ai-accounts/ARCHITECTURE.md](docs/ai-accounts/ARCHITECTURE.md) |
| Internationalization | [docs/i18n.md](docs/i18n.md) |

<div align="center"><sub>Built for harness engineering.</sub></div>
