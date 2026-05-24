# PR-E — Sidebar IA polish (operator-feel pass)

**Parent spec:** `2026-05-21-sidebar-ia-redesign-design.md`
**Predecessors:** PR-B (#150), PR-C (#151), PR-D (#152) — all merged.
**Driver:** User feedback after living with PR-B/C/D — "hierarchy design is
not smooth as what i feel an user."

## Premise

PR-A through PR-D collapsed the sidebar by the *domain audit*. Several of
those placements were technically defensible (Marketplace next to the
assets it surfaces, External Integrations as its own section, Scheduling
as a flat link, MCP Servers as a full label) but **don't match the
operator's mental model** when they actually click around. PR-E fixes
the five concrete misfits the user named, with no other scope.

## In scope (exactly five changes)

| # | Change | Rationale |
|---|--------|-----------|
| 1 | Marketplace: out of Forge → own top-level slot | Forge = local assets you manage; Marketplace = where you go to *get* them. Different lifecycle phases, shouldn't be siblings. |
| 2 | External Integrations → System group; rename label to "Integrations" | Slack/Jira/Linear/Notification Channels are system-wiring concerns, not a top-level domain. Standalone section overweights them. |
| 3 | Scheduling → Work group | Operator-monitoring action lives with the other Work surfaces. |
| 4 | Dashboards → Work group | Same reason — Dashboards is the daily Work view, not a Watch-tier surface. |
| 5 | "MCP Servers" → "MCPs" | Tighter label parity with Plugins / Skills / Hooks / Rules / Commands. |

## Out of scope

- No new routes; no view renames; no submenu reshuffles inside the
  affected groups.
- Marketplace stays one flat link — no submenu, no tab reshuffle.
- System group's existing children (AI Backends + whatever else is
  there) stay where they are; Integrations items append below.
- Work group's existing children (Sketch) stay where they are; Dashboards
  and Scheduling append below Sketch in that order.

## File-by-file plan

### `frontend/src/components/layout/AppSidebar.vue`

**A. Reorder sidebar sections**

Current order (top → bottom):
1. Watch Tower (section)
2. Dashboards (expandable — currently above Work label)
3. Scheduling (flat link — currently above Work label)
4. Work label + Sketch
5. Organization
6. Forge (contains Marketplace flat link)
7. Triggers
8. External Integrations
9. History
10. Resources
11. System (AI Backends)

New order:
1. Watch Tower (section)
2. **Work label + Sketch + Dashboards + Scheduling** (moves: Dashboards block + Scheduling flat link slot under Work, after Sketch)
3. Organization
4. Forge (Marketplace **removed** from here)
5. **Marketplace** (new top-level flat link, between Forge and Triggers — keeps it adjacent to the asset surfaces it feeds)
6. Triggers
7. History
8. Resources
9. System (with Integrations as a child block)

**B. Rename MCP Servers → MCPs**

`AppSidebar.vue:718` — `<SidebarGroupToggle label="MCP Servers"` → `label="MCPs"`.
Update the aria-label on the submenu region as well (line ~723).
Do not change the route name or the page title; only the sidebar label.

**C. Marketplace promotion**

Move the `<SidebarFlatLink label="Marketplace">` block (currently
`AppSidebar.vue:739-768` ish — flat link inside Forge) to between the
Forge group's closing block and the Triggers `SidebarSectionLabel`.
No state changes — the activity classification (`sidebarActive('marketplace')`)
already works as a flat link.

**D. External Integrations → System group, rename "Integrations"**

- Delete the `SidebarSectionLabel label="External Integrations"` at line
  ~966.
- Move the entire `SidebarGroupToggle` + its `nav-submenu` div from
  ~967-989 to **just below** the AI Backends group inside the System
  section.
- Rename the toggle's `label="External Integrations"` → `label="Integrations"`.
- Rename the `aria-label="External Integrations"` on the submenu region
  → `aria-label="Integrations"`.
- Keep `expandedSections.externalIntegrations` state key + the
  `isExternalIntegrationsSectionActive()` function names (renaming
  those is churn without payoff — the user-visible label is what
  matters).

**E. Anchor logic — Marketplace tracker arrays**

After moving Marketplace out of Forge, audit the helper functions at
lines 88/91/94/109/183/187/207/223 in `AppSidebar.vue` that include
`'marketplace'` in their inclusion arrays. The Marketplace route name
should remain present in those arrays so the Marketplace tile still
"lights up" the relevant Forge submenu when the user is sitting on
Marketplace — **but** that crossover is what we're undoing. Drop
`'marketplace'` from those Forge-submenu activity checks; Marketplace
is now its own peer and shouldn't paint Plugins/Skills/MCPs/Super-Agents
as "active" at the same time.

### `frontend/src/components/layout/__tests__/AppSidebar.structure.test.ts`

Update the structural assertions to reflect:
- Dashboards + Scheduling inside Work group
- Marketplace as a peer of Triggers (not inside Forge)
- "MCPs" label string
- "Integrations" label inside System

## Verification

- `cd frontend && npm run test:run` (must pass, including sidebar
  structural tests)
- `just build` (vue-tsc, no errors)
- Manual: load `/`, eye the sidebar, confirm five changes visually.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Marketplace activity-cross-painting was load-bearing for some test | Run sidebar tests; if any rely on Marketplace lighting up Plugins/Skills/MCPs/SA, update them — that cross-paint was the bug we're fixing. |
| Moving Dashboards block changes route-active highlighting | The submenu items already use `sidebarActive(...)` per-name; relocation doesn't change name lookups. |
| Reordering breaks visual smoke tests | None at this layer in the project — frontend test suite is happy-dom; no snapshot of the sidebar exists. |
| External Integrations state key + function name kept | Documented above as intentional; renaming is pure churn. |

## Commit shape

One commit, one PR. Diff is mostly mechanical block moves plus four
label-string changes plus one helper-array prune.
