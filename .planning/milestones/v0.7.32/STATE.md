# v0.7.32 State

Status: COMPLETE — shipped PR #87 (2026-05-11).

## Shipped

Same pattern as v0.7.31: ``createCommand`` had no in-flight tracking
on the create modal. The Save button on the detail panel did
(``:disabled="isSaving || !editForm.name.trim()"``), but the modal's
"Create Command" was a plain ``<button type=\"submit\">`` — a double-
click submitted twice and produced duplicate commands.

## Key files touched

- `frontend/src/views/CommandsPage.vue`

## Reference

- PR: #87
- Commit: `bb9d4567`
