# Full Multi-File Skill Package Creation

**Date:** 2026-05-17
**Status:** Approved (scope decisions locked via AskUserQuestion)
**Depends on:** v0.7.76 (`9adedf8` — skills wizard proxy error fix)

## Problem

`SkillCreateWizard` currently only writes a single `SKILL.md` file with
no frontmatter. The conversation collects `{skill_name, description,
triggers, instructions, examples}`; `finalize_skill` renders a
markdown body and saves it under
`{playground}/.claude/skills/{name}/SKILL.md`.

Real Claude Code Skills are **packages**, not lone markdown files.
Anthropic's spec calls for:

* YAML frontmatter at the top of `SKILL.md` (`name`,
  `description`, `license`, `allowed-tools`, `tags`).
* Optional `scripts/` for executable helpers (Python/shell that
  claude invokes via Bash when the skill is active).
* Optional `references/` for long-form docs claude loads on demand
  (the skill body usually references them by relative path).
* Optional `assets/` for static files (templates, fixtures).

The wizard produces nothing portable to claude.ai's marketplace
and nothing that follows the format the rest of the ecosystem uses.

## Goal

The wizard, after the operator confirms, produces a **valid
Anthropic-format skill package** on disk and in the DB. The
operator gets a preview of the full file tree before finalize
(`SkillCreatePreviewDrawer`).

## Decisions (settled — do not re-litigate)

1. **Format:** Anthropic spec compliance. YAML frontmatter + the
   three convention subdirs (`scripts/`, `references/`, `assets/`).
2. **Review step:** preview drawer with collapsible per-file content,
   no inline editing in v1. Operator inspects the tree, clicks
   Create, files land on disk.

## Schema (system-prompt-instructed config block)

Claude emits this between `---SKILL_CONFIG---` markers:

```json
{
  "skill_name": "data-explorer",
  "frontmatter": {
    "description": "Explore tabular datasets and surface key stats.",
    "license": "MIT",
    "allowed_tools": ["Bash", "Read", "Glob"],
    "tags": ["data", "analytics"]
  },
  "body": "Markdown body of SKILL.md (without the frontmatter delimiters).\n\nReference `references/api-cheatsheet.md` for the column-spec syntax. Run `scripts/profile.py` to generate a quick summary.",
  "files": [
    {
      "path": "scripts/profile.py",
      "content": "#!/usr/bin/env python3\n..."
    },
    {
      "path": "references/api-cheatsheet.md",
      "content": "# Column-spec syntax\n..."
    }
  ]
}
```

* `frontmatter` keys are required to include `description`; the others
  are optional. Backend defaults `license: "MIT"`, omits empty
  arrays/strings from the rendered YAML.
* `body` is the post-frontmatter markdown (no `---` delimiters
  inside it). Backend writes:
  ```
  ---
  name: data-explorer
  description: ...
  license: MIT
  allowed-tools:
    - Bash
    - Read
  ---

  Markdown body...
  ```
* `files[].path` must start with `scripts/`, `references/`, or
  `assets/` and must not escape via `..`. Each file is size-capped at
  256 KB. The total package is capped at 50 files. Anything that
  violates returns a 400 with a list of rejected paths.

## Backend changes

`backend/app/services/skill_conversation_service.py`

* `SKILL_CREATION_SYSTEM_PROMPT` rewritten to teach claude the new
  config schema (frontmatter keys, allowed file path prefixes, when
  to add helpers vs references). The prompt body grows ~30 lines.
* `finalize_skill` rewritten:
  1. Parse the config block (same `---SKILL_CONFIG---` markers).
  2. Validate frontmatter (`description` required) + each `files[]`
     entry (path prefix + no `..` + size cap + count cap).
  3. Render YAML frontmatter via PyYAML (already a transitive dep)
     or a hand-rolled dumper for the small set of fields.
  4. Compose `SKILL.md` = frontmatter block + `---` + body.
  5. Write `SKILL.md` + each helper/reference file with directory
     creation. All writes are atomic per-file (write to `.tmp`,
     rename) so a partial failure doesn't leave a half-written package.
  6. Insert `user_skills` row (existing). Metadata JSON gains a
     `files` array listing the package contents (paths only, not
     bodies — that'd blow the DB row size).
* New `preview_finalize` method (companion to `finalize_skill`):
  parses + validates the config block, returns the rendered tree
  without writing to disk. Used by the new preview drawer to show
  the exact files that would land.

New route: `POST /api/skills/conversations/{conv_id}/preview-finalize`
returns `{ skill_md_path, skill_md_content, files: [{path, content,
size_bytes}], warnings: [...] }`. Warnings cover non-fatal issues
(e.g., frontmatter missing `description` — the wizard surfaces these
without blocking).

## Frontend changes

`frontend/src/views/SkillCreateWizard.vue`

* Replaces the `Create Skill` button's direct `finalize()` call with
  a two-step flow: click → opens `SkillCreatePreviewDrawer` → drawer's
  Create button runs `finalize()` and on success closes + shows toast.

`frontend/src/components/skills/SkillCreatePreviewDrawer.vue` (new)

* Reuses the slide-over shape from `ContextPreviewDrawer`
  (`Teleport to="body"`, `useFocusTrap`, escape-to-close, backdrop
  click).
* Calls `POST .../preview-finalize` on open.
* Renders a file tree:
  ```
  📄 SKILL.md          (2.1 KB)
  📁 scripts/
    📄 profile.py      (0.8 KB)
  📁 references/
    📄 api-cheatsheet.md  (1.4 KB)
  ```
  Each entry is a `<details>` element; the operator clicks to expand
  and see the rendered content. SKILL.md gets syntax highlighting
  for the YAML frontmatter; helpers use the file extension to pick
  a highlighter (`python`, `markdown`, etc.).
* Footer: `Create Skill` button. Same `isFinalizing` disabled state
  as the prior button.

`frontend/src/composables/useConversation.ts`

* `previewFinalize()` helper added alongside the existing
  `finalize()`. Returns the tree blob.

## Tests

* `backend/tests/services/test_skill_conversation_service.py` —
  rewrite `test_finalize_skill_writes_md` to assert the new
  frontmatter + multi-file shape; new tests for path-traversal
  rejection, size cap rejection, file count cap, atomic write
  rollback on mid-package failure.
* `backend/tests/routes/test_skills_routes.py` — new test for
  `preview-finalize` route shape.
* Frontend: `SkillCreatePreviewDrawer.test.ts` — tree renders,
  expand/collapse, Create button wiring.

## Migration / rollout

* Existing skills on disk (single-file SKILL.md with no
  frontmatter) keep working — the rest of the codebase reads
  `user_skills.skill_path` and the content directly; no consumer
  cares about the frontmatter presence yet.
* The system-prompt change means new conversations will produce
  the richer schema; old conversations in flight before the deploy
  could emit the legacy single-skill config block. `finalize_skill`
  accepts both schemas as a transition shim (when `frontmatter` /
  `files` keys are missing, fall back to the v0.7.75 rendering).

## Implementation scope estimate

| Area | LOC |
|---|---|
| Backend: system prompt + finalize rewrite + preview route + validation | ~350 |
| Backend tests (5 new test cases) | ~200 |
| Frontend: preview drawer | ~250 |
| Frontend: wizard wiring + composable helper | ~50 |
| Frontend tests | ~120 |
| **Total** | **~970** |
