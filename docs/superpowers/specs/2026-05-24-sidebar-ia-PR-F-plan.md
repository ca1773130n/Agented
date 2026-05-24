# PR-F — Sidebar IA polish, round 2

**Parent spec:** `2026-05-21-sidebar-ia-redesign-design.md`
**Predecessors:** PR-B (#150), PR-C (#151), PR-D (#152), PR-E (#153) — all merged.
**Driver:** User feedback after living with PR-E. Continues the operator-feel
correction loop. This PR partially reverses PR-B's "Triggers as top-level
central abstraction" thesis — the user has decided the practice doesn't
match the audit-driven theory.

## Three changes (exactly)

| # | Change | Rationale |
|---|--------|-----------|
| 1 | Delete the "Watch Tower" section label (dangling — no content under it) and migrate its `error-keys=['triggers']` binding to the Forge section label. | Dead header. Trigger errors should surface where Triggers now lives (Forge). |
| 2 | Reorder Work group: `Dashboards → Sketch → Scheduling` (was `Sketch → Dashboards → Scheduling`). | Dashboards is the daily entry-point — should be on top. |
| 3 | Collapse the Triggers section into Forge: delete the `Triggers` `SidebarSectionLabel`, move the `Triggers` `SidebarGroupToggle` + its ~25-item submenu into the Forge group immediately after Workflows. | Triggers section overweighted itself with 25 facets the operator rarely touches as a section. Collapsing back to a single Forge child surfaces only the entry-point, deep facets remain reachable inside the expandable. |

## Out of scope

- No changes to Triggers submenu contents (all 25 items preserved as-is).
- No state-key renames (`expandedSections.triggers`, `isTriggersSectionActive()` stay).
- No route renames or page renames.
- No other sidebar regroupings.
- Parent design doc (`2026-05-21-sidebar-ia-redesign-design.md`) gets a strikethrough amendment noting PR-B's Triggers-as-section call was reversed by PR-F based on operator-feel feedback. Audit conclusions stay intact (Triggers IS the central abstraction); only the IA expression of that fact is rolled back.

## File-by-file plan

### `frontend/src/components/layout/AppSidebar.vue`

**A. Delete Watch Tower section label (lines 379-385)**

```vue
<SidebarSectionLabel
  label="Watch Tower"
  :error-keys="['triggers']"
  :errors="props.sidebarErrors"
  @retry="(k) => emit('retrySidebarSection', k)"
/>
```

Delete this entire block.

**B. Migrate `error-keys=['triggers']` to Forge section label**

At line ~650 the Forge `SidebarSectionLabel` exists. Add the same
`error-keys`, `errors`, and `@retry` bindings if not already present.
If Forge label already has error-keys, **merge** `'triggers'` into the
existing array — do not overwrite.

Verify by reading the Forge SectionLabel block before editing. If the
pattern there doesn't already include error-keys plumbing, copy the
shape exactly from Watch Tower's binding so the parent retry handler
keeps working for `'triggers'`.

**C. Reorder Work group**

Currently in Work group (after `<div class="nav-section-label">Work</div>`):
1. Sketch (`SidebarFlatLink` at ~387-398)
2. Dashboards (`SidebarGroupToggle` + submenu at ~400-447)
3. Scheduling (`SidebarFlatLink` at ~450+)

New order:
1. Dashboards (move to top of Work group, before Sketch)
2. Sketch
3. Scheduling

Pure block reorder. No state, props, or comments inside the blocks change.
The "PR-E moved it into the Work group" comments stay accurate — they
just describe the group membership, not the order.

**D. Collapse Triggers section into Forge**

Delete:
```vue
<SidebarSectionLabel label="Triggers" />
```
at ~line 861.

Move the entire Triggers `SidebarGroupToggle` block + the `<div v-show="expandedSections.triggers" class="nav-submenu nav-submenu-blocks" ...>` element + closing `</div>` into the Forge group, positioned immediately after the Workflows submenu div closes and before the Plugins `<!-- Plugins (expandable) -->` comment.

The whole moved block:
- `<SidebarGroupToggle label="Triggers" ...>` + icon template + close
- `<div v-show="expandedSections.triggers" class="nav-submenu nav-submenu-blocks" role="region" aria-label="Triggers"> ... </div>`

Preserve exactly:
- All 25 `<button class="submenu-item">` entries.
- The block-divider visual structure (`nav-submenu-blocks` class) — Triggers uses block dividers to group facets visually; keep that intact.
- The `expandedSections.triggers` state key, `isTriggersSectionActive()`, and `toggleSection('triggers')` calls.
- The route-name activity inclusion arrays in the script for Triggers (helper functions referencing trigger route names).

After this move, the section between the moved Triggers block's old position and what comes next (which after PR-E should be External Integrations — wait no, PR-E moved that into System — so after PR-E the next section was History) collapses naturally.

### `frontend/src/components/layout/__tests__/AppSidebar.structure.test.ts`

Update assertions:
- Delete any assertion verifying Watch Tower section label presence.
- Delete any assertion verifying a top-level Triggers SidebarSectionLabel.
- Update Work-group ordering assertions: first child is Dashboards, not Sketch.
- Update Forge-group child enumeration: Triggers now appears in Forge children after Workflows and before Plugins.
- Keep all Triggers submenu-item presence assertions — those items haven't changed, just relocated.

If a test references `'External Integrations'` or `'MCP Servers'` literals, leave alone (those are PR-E concerns, already updated).

### `docs/superpowers/specs/2026-05-21-sidebar-ia-redesign-design.md`

Add a strikethrough amendment in the PR-B section:

> ~~**Goal:** make the IA reflect that Triggers is the central abstraction.~~ **Amended 2026-05-24 (PR-F):** the Triggers-as-top-level-section expression was rolled back. Operator-feel testing across PR-B/C/D/E showed the 25-item section dominated the sidebar without earning its weight at the IA layer (most facets are configured once and rarely revisited). Triggers collapses back to a single Forge child below Workflows; the underlying audit conclusion (Triggers is the central abstraction in the domain model) stands — but the sidebar treats it as one entry-point, not a regional capital.

## Verification

- `cd frontend && npm run test:run` (must pass — sidebar structural tests + any tests using helper functions whose arrays change)
- `cd frontend && npx vue-tsc --noEmit`
- Manual eye-test: load `/`, confirm three changes.

## Risks

| Risk | Mitigation |
|------|------------|
| Migrating `error-keys=['triggers']` to Forge label — Forge label might already have error-keys, in which case append; might not, in which case copy the binding shape. | Read Forge label block first; merge or copy as appropriate. |
| Triggers block move breaks the block-divider styling (`nav-submenu-blocks` class might rely on a specific parent) | The class is on the `<div>` itself, not parent-dependent. Move preserves it. |
| Some helper function references `'watch-tower'` route name | There is no `watch-tower` route — Watch Tower was a dangling label with no content. No helpers to update. |
| Test file has Watch Tower assertion that has no obvious replacement | Just delete it — the section is gone. |

## Commit shape

One commit, one PR. Mostly mechanical: 1 deletion + 1 error-keys merge + 1 reorder + 1 large block move + parent-spec amendment.
