<div align="center">

# Agented

**A meta-harness engineering platform for running a virtual startup with autonomous AI agents.**

Agented gathers the state of the art in AI harness engineering — loop
engineering, agent orchestration, swarms, self-improvement, autoresearch,
persistent memory — into one product- and project-centric operator console.
Think a Hermes-style agent system, but broader, with a WebUI built for
**operating a company**, not just chatting with a model.

[Architecture](docs/self-improving-harness-architecture.md) · [Tutorial](docs/self-improving-harness-tutorial.md) · [Changelog](CHANGELOG.md) · [Security](docs/SECURITY.md) · [Deploy](docs/deploy.md)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](docs/deploy.md#1-render-blueprint)

**Docs in your language:** [한국어](docs/ko/self-improving-harness-architecture.md) · [日本語](docs/ja/self-improving-harness-architecture.md) · [中文](docs/zh/self-improving-harness-architecture.md)

</div>

---

## What Agented is

How to get real, sustained work out of AI agents is being figured out **right
now** — in conference talks, blog posts, and the working notes of the people
building harnesses. Agented's bet is that those ideas shouldn't stay scattered
across one-off scripts and private rigs. It collects them into a single
**meta-harness layer** that sits on top of the coding CLIs (Claude Code, Codex,
Gemini CLI, OpenCode, …) and turns them into the workforce of a **virtual
startup** — organized around **products and projects**, run from one console.

It is **early stage and moving fast**. What's already here:

- **🔁 Loop engineering** — one `LoopSpec` schema and a single executor drive
  every loop pattern (goal-loops, Ralph): an exit ladder (quality-gate →
  stagnation → convergence → budget), per-iteration checkpoints, resume, and
  human gates. → [Architecture](docs/self-improving-harness-architecture.md)
- **🎛 Agent orchestration** — a first-class model of **products → projects →
  teams → agents**, coordinated from one dashboard, each run composed from
  per-project context, accounts, and primitives.
- **🐝 Swarms across many AI accounts** — schedule and hand off work across
  multiple provider accounts (via the `ai-accounts` sidecar), with **auto-routing**
  to the right backend and model.
- **♻️ Self-improvement** — an eval-gated, git-reversible "life-harness" loop
  that evolves the harness's own primitives instead of leaving you to hand-tune
  them.
- **🔬 Autoresearch** — the GRD engine runs research → plan → execute → verify as
  an autonomous, milestone-planned pipeline.
- **🧠 Persistent memory + LLM-wiki** — Tesserae compiles a typed knowledge graph
  of code, docs, and session history (plus generated wiki pages) that grounds
  every retrieval.
- **⏳ Long-horizon agents** — durable per-run state, incremental checkpoints, and
  `--resume` so a run survives crashes and spans days.
- **📊 Observability** — live SSE traces, session events, an audit trail, and
  daily/weekly **activity summaries** of everything the agents did.
- **🧩 Harness sharing & composition** — build harnesses by organizing
  **primitives** (skills, hooks, commands, rules, subagents) in the Forge, and
  share them through a plugin marketplace.
- **📦 Product & project management** — competitor monitoring, discovery, and
  strategy; project planning; and **one-click team-harness setup** per project.
- **🛡 Governance & safety** — a stackable policy engine, OS-level sandboxing with
  deny-by-default egress, and real-time multi-user collaboration.

Underneath, every action an agent takes is checkpointed, attributed to its
source, budget-governed, and verifiable — **provenance, auditability, and
rollback are designed in**, not bolted on.

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

### Deploy the prebuilt image

**Recommended — clone and inspect first** (read the code, *then* run it):

```bash
git clone https://github.com/ca1773130n/Agented && cd Agented
./install.sh                 # pull the prebuilt image + bring up the stack
```

`install.sh` reuses the `docker-compose.yml` it was cloned with, so no code is
fetched-and-executed sight-unseen.

<details>
<summary>Convenience one-liner (less safe)</summary>

Piping a remote script into a shell executes code you haven't read. Only do
this pinned to an **immutable release tag** — the installer then SHA-256
verifies the compose file it downloads and aborts on mismatch:

```bash
curl -fsSL https://raw.githubusercontent.com/ca1773130n/Agented/v0.10.0/install.sh | bash
```

Fetching from the mutable `main` branch is refused unless you explicitly set
`AGENTED_INSTALL_UNVERIFIED=1` (which skips checksum verification and prints a
security warning). See [docs/deploy.md](docs/deploy.md#2-single-install-script).
</details>

```bash
# Update an existing install in one command (image is the update unit)
just self-update
```

The **Deploy to Render** badge above opens the Blueprint guide (web + sidecar +
managed Postgres wired to `DATABASE_URL`). It is **not** one-click from this
standalone repo: the image build needs the sibling `ai-accounts/` tree, so
Render must connect a **parent monorepo** holding both `Agented/` and
`ai-accounts/` (with `render.yaml` at its root). Full setup, including the
optional Postgres story, in **[docs/deploy.md](docs/deploy.md)**
([한국어](docs/deploy.ko.md)).

> **First run:** the **first** account to register becomes admin. Set
> `AGENTED_DISABLE_SIGNUP=1` once you've registered — always before exposing the
> instance to an untrusted network.

## How the pieces fit

Products and projects are the top of the model; teams and agents do the work;
loops, memory, policies, and primitives are the machinery each run draws on.
**Triggers** (webhooks, GitHub events, schedules, or a manual run) are just the
delivery mechanism — the product is the autonomous-agent workflow they kick off.

| Layer | Stack | Port |
|---|---|---|
| **Backend** | Litestar (gunicorn / UvicornWorker), raw SQLite (experimental Postgres), subprocess + SSE | `:20000` |
| **Frontend** | Vue 3 + TypeScript operator console | `:3000` |
| **Sidecar** | `ai-accounts` — AI-backend identity, credentials & login flows | `:20001` |
| **Memory** | Tesserae typed knowledge graph + CodeGraph symbol index | — |

## Configuration

| Variable | Description | Default |
|---|---|---|
| `AGENTED_DISABLE_SIGNUP` | Close open self-registration (set after the first admin) | unset (open) |
| `DATABASE_URL` | Postgres URL to use the experimental PG adapter (unset ⇒ SQLite) | unset (SQLite) |
| `AGENTED_SANDBOX` | Opt into OS-level harness sandboxing (bwrap / seatbelt) | unset (off) |
| `AI_ACCOUNTS_API_KEY` | Token for the `ai-accounts` sidecar | reuse admin key |

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
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| Self-improving harness — architecture | [docs/self-improving-harness-architecture.md](docs/self-improving-harness-architecture.md) |
| Self-improving harness — tutorial | [docs/self-improving-harness-tutorial.md](docs/self-improving-harness-tutorial.md) |
| Harness-1 integration (research) | [docs/harness-1-integration.md](docs/harness-1-integration.md) |
| Security | [docs/SECURITY.md](docs/SECURITY.md) |
| Deploy — Render Blueprint / install / self-update | [docs/deploy.md](docs/deploy.md) · [한국어](docs/deploy.ko.md) |
| Deploy — runbook · backup · secrets | [runbook](docs/deploy/RUNBOOK.md) · [backup](docs/deploy/BACKUP.md) · [secrets](docs/deploy/SECRETS.md) |
| ai-accounts sidecar | [docs/ai-accounts/ARCHITECTURE.md](docs/ai-accounts/ARCHITECTURE.md) |
| Internationalization | [docs/i18n.md](docs/i18n.md) |

<div align="center"><sub>Harness engineering for a one-person startup — and the teams that come after.</sub></div>
