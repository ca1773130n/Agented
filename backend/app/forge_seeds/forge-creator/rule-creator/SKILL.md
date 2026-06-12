---
name: rule-creator
description: Scaffold a new always-on rule under .claude/ from within an Agented-driven session. Use when the user asks to add a standing rule, guardrail, or convention the agent must always follow.
---

# Rule Creator

Authors a standing rule as a markdown file under `.claude/rules/`. Rules are
always-loaded guidance (conventions, guardrails) — unlike skills, they are not
matched on demand. Files only; Agented imports the file after the session ends.

## When to Use

- The user asks to "add a rule", "always do X", or "never do Y".
- A convention must apply to every future session in this project (coding style,
  security guardrail, naming convention).

Do NOT use for on-demand procedures (use skill-creator) or for invokable
commands (use command-creator).

## Procedure

1. Choose a kebab-case `<rule-name>`.
2. Create `.claude/rules/<rule-name>.md`.
3. Write YAML frontmatter with `name` and `description`.
4. Add sections: `## When to Use`, `## Procedure`, `## Pitfalls`,
   `## Verification`.
5. State the rule imperatively ("Always…", "Never…") and keep it short — rules
   are always in context, so they cost tokens every turn.

## Pitfalls

- Writing a long essay — rules load every turn; keep them tight.
- Phrasing as a suggestion rather than an imperative.
- Placing the file outside `.claude/rules/` — it will not be imported.
- Encoding project-specific secrets — rules are shared content.

## Verification

- `.claude/rules/<rule-name>.md` exists.
- Frontmatter parses with non-empty `name` + `description`.
- The rule is stated imperatively and concisely.
