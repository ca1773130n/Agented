# v0.7.79 State

Status: COMPLETE — shipped PR #122 (2026-05-17).

## Shipped

Previously the Create button was ``v-if``'d out until claude
emitted a SKILL_CONFIG block, so a new operator couldn't tell
whether the button was missing, broken, or just not ready — and
had no signal as to what to type to make it appear.

## Key files touched

- `frontend/src/views/SkillCreateWizard.vue`

## Reference

- PR: #122
- Commit: `51e097cb`
