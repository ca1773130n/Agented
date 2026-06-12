---
name: subagent-creator
description: Scaffold a new subagent under .claude/agents/ from within an Agented-driven session. Use when the user asks to create a specialized delegate agent with its own role and instructions.
---

# Subagent Creator

Authors a subagent as a markdown file under `.claude/agents/`. A subagent is a
named, specialized delegate the primary agent can hand focused work to. Files
only; Agented's session-completion import handler picks it up afterwards.

## When to Use

- The user asks to "create a subagent", "add a specialized agent", or "make a
  delegate for X".
- A distinct role (reviewer, researcher, tester) should run with its own scoped
  instructions and tool access.

Do NOT use for reusable procedures (use skill-creator) or always-on conventions
(use rule-creator).

## Procedure

1. Choose a kebab-case `<subagent-name>`.
2. Create `.claude/agents/<subagent-name>.md`.
3. Write YAML frontmatter with `name` and `description`. The `description` MUST
   state the subagent's specialty and when to delegate to it.
4. Add sections: `## When to Use`, `## Procedure`, `## Pitfalls`,
   `## Verification`.
5. Write the body as the subagent's system prompt: role, scope, constraints, and
   what it should return to the caller.

## Pitfalls

- Overlapping responsibility with an existing subagent — keep roles distinct.
- A vague `description` — the primary agent never delegates to it.
- Writing the file outside `.claude/agents/` — it will not be imported.
- Granting an over-broad role or embedding secrets in the prompt.

## Verification

- `.claude/agents/<subagent-name>.md` exists.
- Frontmatter parses with non-empty `name` + `description`.
- The body is a self-contained system prompt with a clear, narrow role.
