# PR-G — Silent-success stubs cleanup

**Driver:** Joint Claude/codex wiring review (`.planning/wiring-review/{claude,codex}-findings.md`) found 3 backend route groups that return 200 with empty/fake data while the UI treats them as "feature working." Operators see green where there's nothing.

## In scope (exactly 3 surfaces)

| # | Surface | Backend (file:line) | UI consumer | Today's lie |
|---|---|---|---|---|
| 1 | **Anomaly Detection** | `executions.py:474,479` | `AnomalyDetectionCard.vue` (Quality lane) | "No active anomalies — all executions look normal" |
| 2 | **Execution Quotas** | `executions.py:484-503` (4 handlers) | `ExecutionQuotaControls.vue` (settings page) | Create/update/delete fake-succeed; nothing persists |
| 3 | **Report Digests** | `leaf_crud_c.py:265,284` (create+update) | `ReportDigestsPage.vue` (reports section) | "Digest settings saved" — nothing persists |

## Approach: return 501 + UI banner

**Principle:** for features that aren't built, the backend should tell the truth (`501 Not Implemented`), and the UI should render a static "Feature not yet enabled" banner instead of pretending. This is reversible — when the feature ships, replace the 501 with a real handler and remove the banner.

### Backend changes

For each stub handler:
- Change return statement to raise `HTTPException(status_code=501, detail="Feature not yet enabled", extra={"feature": "<feature-key>"})`.
- Keep the route registered so the URL still resolves (so the UI gets 501, not 404).
- Feature keys: `anomaly-detection`, `execution-quotas`, `report-digests`.

**Special case** — `GET /executions/quotas` and `GET /digests` currently return `{rules: []}` / `{digests: []}` and the UI renders honest empty states. **Keep these as-is** (no behavior change). Only the **mutating** handlers + the anomalies endpoints become 501.

**Final touch:** for `GET /executions/anomalies`, returning empty IS the lie (UI says "everything normal"). So that one also flips to 501.

Handlers becoming 501:
- `executions.py:474` `execution_anomalies` (GET) → 501
- `executions.py:479` `acknowledge_anomaly` (POST) → 501
- `executions.py:490` `create_execution_quota` (POST) → 501
- `executions.py:495` `update_execution_quota` (PUT) → 501
- `executions.py:501` `delete_execution_quota` (DELETE) → 501
- `leaf_crud_c.py:265` `create_digest` (POST) → 501
- `leaf_crud_c.py:284` `update_digest` (PUT) → 501

Handlers staying as honest empty reads:
- `executions.py:485` `execution_quotas` (GET) — unchanged
- `leaf_crud_c.py:260` `list_digests` (GET) — unchanged

### Frontend changes

A tiny shared helper:

```ts
// frontend/src/services/notImplemented.ts
export function isNotImplemented(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const status = (err as { status?: number; response?: { status?: number } }).status
    ?? (err as { response?: { status?: number } }).response?.status;
  return status === 501;
}
```

Per-surface UI updates:

1. **`AnomalyDetectionCard.vue`** — on fetch:
   - If 501: set local `disabled = true` + show banner "Anomaly detection is not yet enabled." in place of the current list/empty-state. Don't show the demo-on-failure fallback either (which today is fired on network error; 501 should NOT trigger demo).
   - Otherwise: existing flow.

2. **`ExecutionQuotaControls.vue`** — on create/update/delete responses:
   - If 501: show one-time toast/banner "Quota enforcement is not yet enabled." Disable the create form + edit/delete buttons.
   - Page-level: detect on first mount (try a no-op probe? simpler: probe via attempted GET — already returns empty, so we don't know). Instead: try the GET; if it returns empty, fall through to a disabled-state header "Quota enforcement is in preview — changes are not persisted (501)."
   - Simplest: just disable the form globally and show the banner unconditionally on this page (since per the plan, the mutating endpoints all return 501).

3. **`ReportDigestsPage.vue`** — same pattern as Quotas:
   - On create/update: if 501, show banner "Digest delivery is not yet enabled." Disable create/edit form.

To keep the impl tight, I'll use the "disable globally" approach (instead of trying to detect per-request) for Quotas + Digests, since we KNOW all mutating endpoints return 501. AnomalyDetectionCard uses per-request detection since its GET also returns 501.

### Tests

- Backend: existing tests for these handlers (if any) will fail when expecting 200; update them to expect 501. Search: `grep -rn "execution_anomalies\|acknowledge_anomaly\|execution_quotas\|execution_quota\|create_digest\|update_digest" backend/tests/`.
- Frontend: add minimal tests:
  - `AnomalyDetectionCard.test.ts` — mock 501 response, assert disabled banner renders.
  - Tests for the 2 pages: assert mount renders the banner.

## Out of scope

- Building actual anomaly detection, quota enforcement, or digest delivery (each is multi-week work).
- Deleting the routes/pages (we preserve them as a stable shape for future implementation).
- Touching any of the other stubs codex flagged as honest empty-states (`team_leaderboard`, `list_digests` read, `bot_sla` read).
- Removing `ExecutionQuotaControls.vue` from the router (it's already orphan per the audit; doesn't matter that it's not in the sidebar).

## Verification

- `cd backend && uv run pytest` — must pass (including updated tests).
- `cd frontend && npm run test:run` — must pass.
- `just build` — clean.
- Manual: visit `/dashboards/quality` and confirm the AnomalyDetectionCard shows "not enabled" banner instead of "no anomalies."

## Risks

| Risk | Mitigation |
|------|------------|
| Frontend treats 501 as a generic error (red toast / retry loop) | The `isNotImplemented` helper short-circuits before generic error handling. |
| Banner copy too negative ("not enabled" sounds broken) | Use neutral wording: "Coming soon" or "Not yet available in this build." Pick "Not yet enabled in this deployment." |
| Tests reference these endpoints elsewhere | Run grep before impl; update test fixtures. |
| Operators have muscle memory for the Anomaly card showing all-green | Banner replaces the all-green view, surfacing the gap honestly. That's the goal. |

## Commit shape

One commit, one PR. Backend handler changes (~7 routes flipped to 501), tiny TS helper, three Vue components updated, test updates.
