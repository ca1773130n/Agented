# Hive

A tool for Harness engineering to organize teams, agents, and automation into a working structure — whether that's a real business team or a virtual one.

Hive gives you a dashboard to define products, projects, and teams, then wire up AI agents, bots, skills, and webhooks to do the work.

## Getting Started

Requires [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/).

```bash
# Install everything
just setup

# Run backend and frontend in separate terminals
just dev-backend    # http://localhost:20000
just dev-frontend   # http://localhost:3000
```

API docs are at http://localhost:20000/docs once the backend is running.

## What It Does

**Organization** — Define products, projects, and teams. Assign teams to projects, link projects to products.

**Agents** — Design AI agents with roles, goals, and skills. Run them through conversations or trigger them automatically.

**Bots** — Webhook-driven automation. Bots listen for events (webhooks, GitHub PRs, schedules) and run AI CLI tools with templated prompts.

**Plugins, Skills, Hooks, Commands, Rules** — Composable building blocks. Create skills for agents, hooks for event-driven logic, commands for reusable actions, and rules for validation.

## Configuration

| Variable | Description | Default |
|---|---|---|
| `HIVE_DB_PATH` | SQLite database path | `backend/hive.db` |
| `SECRET_KEY` | Flask secret key | Auto-generated |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed origins | `*` |

## Running Tests

```bash
# Backend
cd backend && uv run pytest

# Frontend
cd frontend && npm run test:run
```
