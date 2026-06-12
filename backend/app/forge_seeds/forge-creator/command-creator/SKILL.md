---
name: command-creator
description: Scaffold a new slash command under .claude/commands/ from within an Agented-driven session. Use when the user asks to create an invokable /command shortcut for a prompt or workflow.
---

# Command Creator

Authors a slash command as a markdown file under `.claude/commands/`. A command
is an invokable, named prompt template the user triggers with `/name`. Files
only; Agented imports the command after the session ends.

## When to Use

- The user asks to "make a /command", "add a slash command", or "create a
  shortcut for this prompt/workflow".
- A frequently-repeated prompt should become a one-word invocation.

Do NOT use for always-on conventions (use rule-creator) or for event-driven
automation (use hook-creator).

## Procedure

1. Choose a kebab-case `<command-name>` — this becomes `/<command-name>`.
2. Create `.claude/commands/<command-name>.md`.
3. Write YAML frontmatter with `name` and `description`.
4. Add sections: `## When to Use`, `## Procedure`, `## Pitfalls`,
   `## Verification`.
5. Write the command body as the prompt template the harness will execute when
   invoked. Use `$ARGUMENTS` for user-supplied input where supported.

## Pitfalls

- Colliding with an existing command name.
- Ambiguous argument handling — document expected `$ARGUMENTS`.
- Writing the file outside `.claude/commands/` — it will not be imported.
- Embedding credentials in the template.

## Verification

- `.claude/commands/<command-name>.md` exists.
- Frontmatter parses with non-empty `name` + `description`.
- The body is a coherent, invokable prompt template.
