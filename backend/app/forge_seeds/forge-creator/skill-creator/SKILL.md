---
name: skill-creator
description: Scaffold a new agentskills.io-compatible skill under .claude/skills/ from within an Agented-driven session. Use when the user asks to create, author, or add a reusable skill.
---

# Skill Creator

Authors a new skill as a `SKILL.md` file under `.claude/skills/<skill-name>/`.
Files only — no API calls or credentials are used in-session; Agented's
session-completion import handler picks the file up afterwards.

## When to Use

- The user asks to "create a skill", "make a skill for X", or "add a reusable
  capability".
- A repeated multi-step procedure should be captured as a named skill so future
  sessions can invoke it.

Do NOT use for one-off instructions, rules (use rule-creator), or slash
commands (use command-creator).

## Procedure

1. Choose a kebab-case `<skill-name>` that names the capability.
2. Create `.claude/skills/<skill-name>/SKILL.md`.
3. Write YAML frontmatter with exactly `name` and `description` keys. The
   `description` MUST state both what the skill does and when to use it (this is
   what the agent matches against at dispatch time).
4. Add the body sections: `## When to Use`, `## Procedure`, `## Pitfalls`,
   `## Verification`.
5. Keep the procedure concrete and ordered; reference real file paths.

## Pitfalls

- Vague `description` — the skill never gets selected. Name the trigger.
- Writing the file outside `.claude/skills/` — it will not be imported.
- Embedding secrets or tokens — skills are content, not credentials.
- Duplicating an existing skill name — pick a distinct kebab-case name.

## Verification

- `.claude/skills/<skill-name>/SKILL.md` exists.
- The frontmatter parses as YAML and has non-empty `name` + `description`.
- All four body sections are present.
