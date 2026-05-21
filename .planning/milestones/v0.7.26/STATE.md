# v0.7.26 State

Status: COMPLETE — shipped PR #81 (2026-05-10).

## Shipped

The "Invalid Date" leak in chat bubbles (v0.7.23) was just one
instance of a pattern that ships in 50+ files: every page rolls its
own ``new Date(x).toLocale*()`` call, and SQLite-format timestamps
(``"2026-05-10 12:34:56"`` without ISO ``T``/``Z``) silently produce
an Invalid Date object. ``toLocaleString()`` on it returns the
literal string ``"Invalid Date"`` without throwing — try/catch
guards never fire — and the bad text leaks into the UI.

## Key files touched

- `frontend/src/components/monitoring/BackendAccountList.vue`
- `frontend/src/components/monitoring/HistoricalSessionViewer.vue`
- `frontend/src/components/product/ProductActivityFeed.vue`
- `frontend/src/components/product/ProductDecisionLog.vue`
- `frontend/src/components/projects/HarnessStatusSection.vue`
- `frontend/src/components/settings/MarketplaceSettings.vue`

## Reference

- PR: #81
- Commit: `f5518f58`
