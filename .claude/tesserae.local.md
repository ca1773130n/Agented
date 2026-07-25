---
hooks:
  session_end: false
---

# Tesserae plugin hooks — local overrides

`session_end: false` — the session-end hook fired a **full** `tesserae compile`
every time a harness session closed. On this project that is a multi-hour job
(137 docs, ~4.5h), so every session close queued heavy work; one such run wedged
on a single doc for 9+ hours holding `.tesserae/compile.lock`, which is what froze
the index for 12 days, and its append-only log reached 121 MB.

Compiles here are run deliberately — detached from the CLI, or incrementally via
the backend (`compile_workspace` is `--changed-only` by default).
