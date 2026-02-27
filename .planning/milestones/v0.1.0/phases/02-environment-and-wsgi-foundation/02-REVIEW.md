---
phase: 02-environment-and-wsgi-foundation
wave: all
plans_reviewed: [02-01, 02-02]
timestamp: 2026-02-28T03:30:00Z
blockers: 0
warnings: 1
info: 5
verdict: warnings_only
---

# Code Review: Phase 02 (Environment and WSGI Foundation)

## Verdict: WARNINGS ONLY

All plan tasks were executed faithfully with no unplanned deviations. Code changes match the plan specifications, the research recommendations, and known pitfalls. One warning regarding the 02-02 SUMMARY.md not listing explicit commit hashes (only messages), which slightly reduces traceability compared to the 02-01 SUMMARY.md format.

## Stage 1: Spec Compliance

### Plan Alignment

**Plan 02-01 (3 tasks, wave 1):**

| Task | Plan Description | Commit | Status |
|------|-----------------|--------|--------|
| Task 1: Add dependencies | gevent, python-dotenv, APScheduler, pytz to pyproject.toml | `9be53aa` feat(deps): add gevent, python-dotenv, APScheduler, pytz | Exact match |
| Task 2: SECRET_KEY + dotenv | _get_secret_key() in __init__.py, load_dotenv in run.py, .gitignore | `bbc6033` feat(config): implement SECRET_KEY persistence and dotenv loading | Exact match |
| Task 3: gunicorn.conf.py | Create config with workers=1, gevent, no preload_app | `53056a7` feat(deploy): add gunicorn.conf.py with gevent worker configuration | Exact match |

All three tasks have corresponding commits. Files modified in git (`backend/pyproject.toml`, `backend/uv.lock`, `backend/app/__init__.py`, `backend/run.py`, `backend/gunicorn.conf.py`, `.gitignore`) exactly match the SUMMARY claims. `backend/uv.lock` is an expected side effect of `uv sync` and is appropriately listed.

**Plan 02-02 (2 tasks, wave 2):**

| Task | Plan Description | Commit | Status |
|------|-----------------|--------|--------|
| Task 1: .env.example | Document all env vars from codebase audit | `2807d59` docs(env): add .env.example with all documented environment variables | Exact match |
| Task 2: justfile + supervisor configs | Update deploy target, add systemd + launchd configs | `d8505ed` feat(deploy): gunicorn deploy target and process supervisor configs | Exact match |

Files modified in git (`backend/.env.example`, `justfile`, `deploy/agented.service`, `deploy/com.agented.backend.plist`) exactly match SUMMARY claims.

Both SUMMARYs report zero deviations. Git diffs confirm no unexpected changes.

No issues found.

### Research Methodology

The implementation follows 02-RESEARCH.md recommendations precisely:

1. **Recommendation 1 (Gunicorn + gevent):** `gunicorn.conf.py` sets `worker_class = "gevent"`, `workers = 1`, matching the research rationale about in-memory SSE state (`/Users/edward.seo/dev/private/project/harness/Agented/backend/gunicorn.conf.py` lines 28-36).

2. **Recommendation 2 (python-dotenv):** `load_dotenv()` is called at the top of `run.py` (line 6) before any app imports, and also at the top of `gunicorn.conf.py` (line 20), matching Pattern 1 from research.

3. **Recommendation 3 (SECRET_KEY persistence):** `_get_secret_key()` in `/Users/edward.seo/dev/private/project/harness/Agented/backend/app/__init__.py` (lines 25-52) implements the exact three-tier fallback: env var > `.secret_key` file > generate-and-persist. Matches Pattern 2 from research, including `chmod(0o600)` and `OSError` fallback.

4. **Recommendation 4 (monkey patching):** `preload_app` is intentionally NOT set (only appears in a comment at line 49-52 of gunicorn.conf.py explaining why), matching Pitfall 3 from research.

5. **Pitfall 1 (APScheduler in pyproject.toml):** APScheduler and pytz are now explicit dependencies in pyproject.toml.

6. **Pitfall 5 (.env.example):** `.env.example` created with 18 variables across 11 sections, exceeding the plan's minimum of 15 variables.

No issues found.

### Context Decision Compliance

No CONTEXT.md file exists for Phase 02. The Phase 01 CONTEXT.md decisions (about web UI patterns, AI interaction model, etc.) are not relevant to this infrastructure phase. No locked decisions to check.

N/A -- no CONTEXT.md for this phase.

### Known Pitfalls (KNOWHOW.md)

KNOWHOW.md at `/Users/edward.seo/dev/private/project/harness/Agented/.planning/milestones/v0.1.0/research/KNOWHOW.md` is an empty template with no populated entries. No pitfalls to cross-reference.

The phase-specific research (`02-RESEARCH.md`) documents its own pitfalls (1-5), all of which are addressed as noted in the Research Methodology section above.

N/A -- KNOWHOW.md is empty.

### Eval Coverage

The evaluation plan at `/Users/edward.seo/dev/private/project/harness/Agented/.planning/milestones/v0.1.0/phases/02-environment-and-wsgi-foundation/02-EVAL.md` defines 12 sanity checks (S1-S12). All checks reference correct file paths and interfaces that exist in the implementation:

- S1 references `import gevent; import dotenv; import apscheduler; import pytz` -- all four are in pyproject.toml
- S2 references `gunicorn --check-config -c gunicorn.conf.py` -- file exists at correct path
- S3 references `workers` and `worker_class` variables -- both present in gunicorn.conf.py
- S4 checks `preload_app` absence -- correctly only in comments
- S5 references `load_dotenv` and `create_app` in run.py -- both present
- S6 references `_get_secret_key` via `create_app().config['SECRET_KEY']` -- function exists
- S7 references `.gitignore` entries -- both `.env` and `backend/.secret_key` present
- S8 references env var names in `.env.example` -- all 10 checked vars are present
- S9 references `gunicorn` in justfile -- present in deploy recipe
- S10 references `dev-backend` recipe -- preserved with `python run.py --debug`
- S11 references backend pytest -- no test files were modified, baseline should hold
- S12 references `Restart=on-failure`, `RestartSec=3`, `KeepAlive` -- all present in respective files

The two deferred evaluations (DEFER-02-01 for SSE load testing, DEFER-02-02 for workers=1 assertion) are properly scoped to future phases.

No issues found.

## Stage 2: Code Quality

### Architecture

All new code follows existing project patterns:

- **`backend/app/__init__.py`:** The `_get_secret_key()` helper follows the existing pattern of module-level helper functions before `create_app()`. Uses `os`, `secrets`, `Path` -- all standard imports already present or trivially added. The only config change inside `create_app()` is a single-line substitution (`_get_secret_key()` replacing `os.environ.get("SECRET_KEY") or secrets.token_hex(32)`).

- **`backend/run.py`:** The `load_dotenv()` call is placed at the absolute top (after shebang/docstring), before all other imports. This is the correct pattern per python-dotenv docs and does not interfere with the existing signal handler and atexit registration logic.

- **`backend/gunicorn.conf.py`:** New file at the correct level (sibling to `run.py`). Uses `load_dotenv()` at the top and `os.environ.get()` for configurable values, consistent with the 12-factor pattern.

- **`.env.example`:** Follows industry-standard format -- commented-out variable assignments with section headers and descriptions.

- **`deploy/` directory:** New directory at project root for deployment configs. Clean separation from `backend/` and `frontend/`.

- **`justfile`:** Minimal, targeted change to the deploy recipe. `dev-backend` preserved. No unrelated changes.

No duplicate implementations introduced. No conflicting patterns.

Consistent with existing patterns.

### Reproducibility

This phase is infrastructure configuration, not experimental code. No seeds, random states, or model training involved. The only "randomness" is `secrets.token_hex(32)` in `_get_secret_key()`, which is explicitly designed to persist its output (to `.secret_key`) for reproducibility across restarts. This is correct behavior.

N/A -- no experimental code.

### Documentation

**`gunicorn.conf.py`:** Excellent documentation. The module docstring (lines 1-16) explains the `workers=1` constraint with specific service names and the CONCERNS.md reference. Inline comments explain each configuration value's purpose. The `preload_app` anti-pattern is explicitly documented in a comment block (lines 49-52) referencing 02-RESEARCH.md Pitfall 3.

**`_get_secret_key()`:** Clear docstring with the three-tier priority explained. Inline comments mark each tier.

**`.env.example`:** Each variable has a description comment with type, default, and purpose. Organized into 11 logical sections.

**`deploy/agented.service`:** Header comment block with install/enable/start/logs commands. Key points documented inline.

**`deploy/com.agented.backend.plist`:** XML comment block with install/load/unload instructions.

Adequate.

### Deviation Documentation

Both SUMMARYs report zero deviations. Git history confirms:

- **02-01 SUMMARY:** Claims 3 commits (`9be53aa`, `bbc6033`, `53056a7`). All three verified in git with matching messages and file lists. No extra files modified.

- **02-02 SUMMARY:** Claims 2 commits (by message only: `docs(env):...` and `feat(deploy):...`). Commits `2807d59` and `d8505ed` verified in git with matching messages and file lists. No extra files modified.

- **Additional commits:** `1e978e9` (docs: 02-01 summary + STATE.md update) and `7f8574c` (docs: 02-02 summary + STATE.md update) are documentation commits for the SUMMARY.md files themselves and STATE.md updates, which is expected administrative overhead.

- **02-02 SUMMARY extra env vars:** The SUMMARY documents that 3 additional variables (`CODEX_HOME`, `GEMINI_CLI_HOME`, `OPENCODE_HOME`) were discovered during the codebase audit beyond the plan's original 15. These are present in `.env.example` (lines 44-53) under "External Tool Homes". The SUMMARY properly documents this as a "Decision" rather than a deviation. This is appropriate -- the plan said "audit all `os.environ.get()` calls... to ensure completeness", so finding additional variables is executing the plan faithfully, not deviating from it.

SUMMARY.md matches git history.

## Findings Summary

| # | Severity | Stage | Area | Description |
|---|----------|-------|------|-------------|
| 1 | WARNING | 2 | Deviation Documentation | 02-02-SUMMARY.md does not include explicit commit hashes in its `commits` frontmatter field (unlike 02-01-SUMMARY.md which lists all three hashes). Commit messages are listed inline but hashes are absent from the YAML frontmatter. |
| 2 | INFO | 1 | Plan Alignment | 02-02 SUMMARY documents 3 additional env vars (CODEX_HOME, GEMINI_CLI_HOME, OPENCODE_HOME) beyond the plan's original 15. Properly documented as a Decision. Plan directed a full codebase audit, so this is correct behavior. |
| 3 | INFO | 2 | Documentation | gunicorn.conf.py references "02-RESEARCH.md Pitfall 3" in a comment (line 52). This is a planning artifact reference inside production code. Not harmful but slightly unusual -- production code typically does not reference planning documents. |
| 4 | INFO | 1 | Eval Coverage | All 12 eval sanity checks (S1-S12) reference correct paths and interfaces. Evaluation is fully runnable against the implementation as delivered. |
| 5 | INFO | 2 | Architecture | Clean separation: all 5 new/modified backend files follow existing patterns. New `deploy/` directory is an appropriate location for process supervisor configs. |
| 6 | INFO | 1 | Research Methodology | All 4 research recommendations and all 5 documented pitfalls are addressed in the implementation. No contradictions found. |

## Recommendations

**For WARNING #1 (02-02-SUMMARY.md missing commit hashes):**
Add the explicit commit hashes to the 02-02-SUMMARY.md frontmatter to match the format used in 02-01-SUMMARY.md. The hashes are `2807d59` and `d8505ed`. This improves traceability when cross-referencing plan execution against git history. This is a documentation-only fix and does not affect code quality or correctness.
