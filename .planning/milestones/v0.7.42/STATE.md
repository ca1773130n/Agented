# v0.7.42 State

Status: COMPLETE — shipped 2026-05-12.

## Shipped

The Sessions tab on a project page surfaces two parallel session
systems: SuperAgent sessions (from /sketch routing) and GRD project
sessions (interactive ``claude`` PTY subprocess). The latter has been
rendered as a monospace terminal block since the feature shipped,
which forces users to read assistant output without markdown,
headings, or code-fence styling — and which produced the user
feedback "i don't want to see terminal text in the grd session".

## Key files touched

- `frontend/src/components/sessions/GrdSessionChatView.vue`
- `frontend/src/views/ProjectManagementPage.vue`
- `backend/tests/test_session_get_or_create.py`

## Reference

- Commit: `1b213647`
