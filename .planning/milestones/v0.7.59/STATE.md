# v0.7.59 State

Status: COMPLETE — shipped 2026-05-16.

## Shipped

The Start/New Session button was gated on the active session being
absent / completed / failed. Clicking a still-active session in the
History sidebar (or a paused one) made the button vanish — leaving
no obvious way to start a fresh conversation without first stopping
the selected one.

## Key files touched

- `frontend/src/components/sessions/SessionControls.vue`

## Reference

- Commit: `d503a940`
