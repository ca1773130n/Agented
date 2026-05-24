# PR-I — DashboardsPage org-overview tiles

**Driver:** Joint wiring review (`.planning/wiring-review/claude-findings.md` F1c). Four org-overview summary dashboards have working Vue components + APIs + WebMCP tools, but DashboardsPage doesn't link to them. They're routes-only and unreachable from the operator's eye-line.

**Scope reduction note:** the original PR-I plan also included an "auth flow gap" fix for `reset-password` / `forgot-password`. On verification (`LoginPage.vue:88`, full `authApi.{forgot,reset}Password` chain, backend `/api/auth/forgot-password` + `/api/auth/reset-password` routes), the flow is **already correctly wired**. The audit script missed it because the routes are reached via `<router-link>` (forgot) and direct URL with `?token=` (reset), not by named navigation. **Auth flow item dropped.**

## In scope (1 change)

Add an "Org overview" row to `DashboardsPage.vue` with 4 tiles routing to the 4 existing org-summary views.

| Tile | route name | view component |
|---|---|---|
| Products | `products-summary` | `ProductsSummaryDashboard.vue` |
| Projects | `projects-summary` | `ProjectsSummaryDashboard.vue` |
| Teams | `teams-summary` | `TeamsSummaryDashboard.vue` |
| Agents | `agents-summary` | `AgentsSummaryDashboard.vue` |

All four already have `useWebMcpTool` registrations (per the audit), so their pages will work as soon as a tile reaches them.

## Implementation

### `frontend/src/views/DashboardsPage.vue`

Add a new section between the 4-lane tiles and the deep-links row. New shape:

```ts
interface OrgTile {
  label: string;
  routeName: string;
  description: string;
  accent: string;
}

const orgTiles: OrgTile[] = [
  {
    label: 'Products',
    routeName: 'products-summary',
    description: 'All products with project + team rollups.',
    accent: 'var(--accent-violet)',
  },
  {
    label: 'Projects',
    routeName: 'projects-summary',
    description: 'All projects with activity + health rollups.',
    accent: 'var(--accent-cyan)',
  },
  {
    label: 'Teams',
    routeName: 'teams-summary',
    description: 'All teams with member + bot rollups.',
    accent: 'var(--accent-emerald)',
  },
  {
    label: 'Agents',
    routeName: 'agents-summary',
    description: 'All agents with run + skill rollups.',
    accent: 'var(--accent-amber)',
  },
];

function openOrgTile(tile: OrgTile) {
  router.push({ name: tile.routeName });
}
```

Template — insert between the lane-tiles section (line ~131) and the deep-links section (line ~133):

```vue
<section class="org-tiles" aria-label="Org-overview dashboards">
  <h2 class="org-tiles__title">Org overview</h2>
  <div class="org-tiles__grid">
    <button
      v-for="tile in orgTiles"
      :key="tile.routeName"
      class="org-tile"
      :data-testid="`org-tile-${tile.routeName}`"
      :style="{ '--tile-accent': tile.accent }"
      @click="openOrgTile(tile)"
    >
      <span class="org-tile__label">{{ tile.label }}</span>
      <span class="org-tile__desc">{{ tile.description }}</span>
    </button>
  </div>
</section>
```

CSS scoped — append:

```css
.org-tiles { display: flex; flex-direction: column; gap: 12px; }
.org-tiles__title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-tertiary); margin: 0; }
.org-tiles__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }

.org-tile {
  display: flex; flex-direction: column; gap: 4px;
  padding: 14px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  text-align: left;
  cursor: pointer;
  color: var(--text-primary);
  transition: border-color 0.15s;
}
.org-tile:hover { border-color: var(--tile-accent); }
.org-tile__label { font-size: 13px; font-weight: 600; }
.org-tile__desc { font-size: 11px; color: var(--text-tertiary); }
```

WebMCP tool update: existing `agented_dashboards_get_state` reports `laneCount` + `deepLinkCount`. Add `orgTileCount` to the returned JSON for completeness.

### Tests

- Update `frontend/src/views/__tests__/DashboardsPage.test.ts` — add assertions:
  - Org-tiles section renders.
  - 4 buttons present with the expected `data-testid` values.
  - Clicking an org tile calls `router.push` with the right `{name}`.

## Out of scope

- Reordering the existing 4 lane tiles.
- Touching the 4 summary view components (they work as-is per audit).
- Adding org tiles to the sidebar — they belong on the dashboard index, not the sidebar.
- Any other "67 dark routes" wiring (PR-J).

## Verification

- `cd frontend && npm run test:run` — must pass (DashboardsPage test updates included).
- `cd frontend && npx vue-tsc --noEmit` — clean.
- Manual: visit `/`, confirm 3 sections (lanes → org overview → quick links).

## Risks

| Risk | Mitigation |
|------|------------|
| One of the 4 org-summary views actually doesn't work despite the audit signal | The wiring review confirmed `api:2 mcp:2` for each — they're real. If a tile reveals a broken page, that's a follow-up bug (not a PR-I regression). |
| Tile UX confusing — operators expect "summary" to mean different things | Tile descriptions explicitly say "rollups" — sets expectations correctly. |

## Commit shape

One commit, one PR. One Vue file + one test file.
