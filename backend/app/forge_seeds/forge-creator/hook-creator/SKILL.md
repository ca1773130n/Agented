---
name: hook-creator
description: Scaffold a new lifecycle hook under .claude/hooks/ from within an Agented-driven session. Use when the user asks to run a command on a harness event (pre/post tool use, session start/stop).
---

# Hook Creator

Authors a lifecycle hook under `.claude/hooks/`. A hook wires a shell command to
a harness event (e.g. PreToolUse, PostToolUse, Stop). Files only; Agented
imports the hook after the session completes.

## When to Use

- The user asks to "run X before/after a tool", "add a hook", or "block Y on
  event Z".
- A guardrail or automation must fire on a harness lifecycle event rather than
  on demand.

Do NOT use for always-on guidance (use rule-creator) or invokable procedures
(use skill-creator / command-creator).

## Procedure

1. Choose a kebab-case `<hook-name>` and the event it binds to.
2. Create `.claude/hooks/<hook-name>.md`.
3. Write YAML frontmatter with `name` and `description`. Name the bound event in
   the `description`.
4. Add sections: `## When to Use`, `## Procedure`, `## Pitfalls`,
   `## Verification`.
5. Document the exact event, matcher, and command. Make the command idempotent
   and fast — hooks run on every matching event.

## Pitfalls

- Slow or blocking commands — they stall every matching event.
- Non-idempotent side effects.
- Writing the file outside `.claude/hooks/` — it will not be imported.
- Hard-coding machine-specific paths or secrets.

## Verification

- `.claude/hooks/<hook-name>.md` exists.
- Frontmatter parses with non-empty `name` + `description`.
- The bound event, matcher, and command are documented.
