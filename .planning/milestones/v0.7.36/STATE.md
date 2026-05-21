# v0.7.36 State

Status: COMPLETE — shipped PR #91 (2026-05-11).

## Shipped

Reported (continued from v0.7.35): "you don't render markdown at all
in the blobs on playground page of a superagent". The v0.7.35 auto-
open-recent-session shipped HistoricalSessionViewer as the default
left panel, which exposed a pre-existing bug — the viewer was
rendering ``{{ msg.content }}`` as plain text. Headings, code fences,
lists, and links in the assistant's stored reply all showed as
literal markdown characters.

## Key files touched

- `frontend/src/components/monitoring/HistoricalSessionViewer.vue`

## Reference

- PR: #91
- Commit: `8c281487`
