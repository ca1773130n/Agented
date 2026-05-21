# PR-C Plan — Marketplace consolidation

**Spec:** `docs/superpowers/specs/2026-05-21-sidebar-ia-redesign-design.md`
**Audit:** `.planning/sidebar-audit.md` (commit `2d22e15`)
**Marketplace audit:** `.planning/marketplace-audit.md` (commit `934e3b3`)

**Plan-review history:**
- Pass 1: codex needs revision — (a) Vue Router redirects must use
  the function form for `?type=X` destinations (static-string form
  doesn't support query-derived destinations); (b) PluginsPage.vue
  and SuperAgentsPage.vue have hardcoded `router.push({ name:
  'explore-X' })` that must be covered (keeping the named redirect
  routes does this transparently — verified-safe); (c) AppSidebar's
  `isXSectionActive` computed arrays need `marketplace` added so the
  section highlights when on the new page; (d) optional: drop the
  mini registry-admin panel from `ExploreSkills` when porting (it
  duplicates Settings → Plugin Marketplaces).

## Spec amendment

The parent spec scoped PR-C as "4 Explore X + 1 Settings 'Add
Marketplace' tab → 1 Marketplace page". The marketplace audit found
this framing is **wrong in three ways**:

1. There are **5 browse pages, not 4** — `SkillMarketplacePage.vue`
   is a 5th (orphan, no sidebar entry).
2. **`BotTemplateMarketplace.vue` is not a marketplace.** Audit shows
   it browses local-DB `BotTemplate` rows and runs an SSE NL Bot
   Creator; `deploy()` instantiates a Trigger; no `marketplaceApi`
   involvement. Belongs under Triggers/Workflows IA, not Marketplace.
   **Out of scope for PR-C.** (Possibly addressed in PR-D or a
   follow-up.)
3. **The Settings tab is not "Add Marketplace".** It's
   `MarketplaceSettings.vue` — full registry admin (CRUD,
   test-connection, deploy, watch/sync, per-registry install via
   `pluginExportApi`). A naive "router link to /marketplace" would
   lose 6+ admin verbs. **Kept as-is in PR-C** (relocation, if any,
   is a follow-up).

**Revised scope:** "5 browse pages → 1 browse page (4 artifact-type
tabs); Settings registry-admin tab kept; BotTemplateMarketplace
left alone."

## Goal

One unified `Marketplace` page replacing the 5 scattered browse
surfaces. Operator picks an artifact type from a tab; the page shows
the right list with the right install action. Old routes redirect to
`/marketplace?type=<X>` so bookmarks survive.

## Components

### `frontend/src/views/MarketplacePage.vue` (new)

- Tab strip at the top: Plugins / Skills / MCP Servers / SuperAgents.
  Active tab via `?type=<x>` query param (sticky, shareable URL).
- Per-tab body composed from a small set of subcomponents (one per
  artifact type) to preserve the per-type behavior the audit
  identified:
  - `MarketplacePlugins.vue` — standard browse + install (port from
    `ExplorePlugins.vue`).
  - `MarketplaceSkills.vue` — preserves the **two-lane layout**:
    "From Marketplace" registry results + "From skills.sh" sources,
    side by side. Port from `ExploreSkills.vue` (don't try to flatten
    the two lanes into one list — audit confirms they're different
    data shapes). **Per codex pre-impl review:** `ExploreSkills.vue`
    has a mini "Manage Marketplace Registries" panel at the bottom
    with Add/Remove registry CRUD (calls `marketplaceApi.create` /
    `delete`). **Do NOT port this panel** — registry admin is owned
    by Settings → Plugin Marketplaces (`MarketplaceSettings.vue`).
    Replace the panel with a small link/note: "Manage registries in
    Settings → Plugin Marketplaces."
  - `MarketplaceMcpServers.vue` — typed install form (server_type
    select / command / args / url / env_json / timeout_ms inputs).
    Port from `ExploreMcpServers.vue`.
  - `MarketplaceSuperAgents.vue` — list + install button that
    surfaces "Coming soon" (the toast-stub install hasn't been
    real since March 2026; don't ship a fake install in the new
    UI). Port the list-rendering from `ExploreSuperAgents.vue`.

These subcomponents are SIBLINGS of `MarketplacePage.vue`, not
nested views. The page is a thin tab-shell that mounts the right
subcomponent based on the active tab; each subcomponent owns its
own API calls + state.

### Deletions

- `frontend/src/views/ExplorePlugins.vue` — replaced by tab content.
- `frontend/src/views/ExploreSkills.vue` — replaced by tab content.
- `frontend/src/views/ExploreMcpServers.vue` — replaced by tab content.
- `frontend/src/views/ExploreSuperAgents.vue` — replaced by tab content.
- `frontend/src/views/SkillMarketplacePage.vue` — orphan, no sidebar
  entry; its data shape (installed+available join on one specific
  registry) is reachable from the Settings admin tab. Delete the
  view + route.

### Route redirects

Add redirects so bookmarks survive. The OLD route entries stay (with
their original `name:`) so any programmatic `router.push({ name:
'explore-X' })` still resolves — but their handler becomes a redirect
to the new Marketplace route with the right query param.

**Critical:** must use Vue Router 4's **function redirect form** (not a
static name string) because the destination needs a query param
derived from the source:

```ts
{
  path: '/plugins/explore',
  name: 'explore-plugins',
  redirect: () => ({ name: 'marketplace', query: { type: 'plugins' } }),
},
```

Apply this shape to:
- `/plugins/explore` (name `explore-plugins`) → `marketplace?type=plugins`
- `/skills/explore` (name `explore-skills`) → `marketplace?type=skills`
- `/mcp-servers/explore` (name `explore-mcp-servers`) → `marketplace?type=mcp-servers`
- `/super-agents/explore` (name `explore-super-agents`) → `marketplace?type=super-agents`
- `/skills/marketplace` (name `skill-marketplace`) → `marketplace?type=skills`

### Programmatic `router.push` call sites that need updating

Per codex pre-impl review, two non-sidebar files push to the old
route names by name. The function-redirect entries above handle
these transparently (the push still resolves; the redirect kicks in
client-side). **Verified-safe approach: keep the redirect entries
and leave these call sites alone:**

- `frontend/src/views/PluginsPage.vue:234` — `router.push({ name:
  'explore-plugins' })`
- `frontend/src/views/SuperAgentsPage.vue:242` — `router.push({ name:
  'explore-super-agents' })`

If a future PR drops the redirect entries (e.g. once we're sure no
bookmarks need them), these two call sites must be updated to
`router.push({ name: 'marketplace', query: { type: '...' } })` in
the same change.

### Out of scope

- **`BotTemplateMarketplace.vue`**: stays as-is. Audit shows it's
  semantically a Triggers/Workflows surface, not a marketplace.
  Sidebar relocation is a follow-up (probably PR-D or a separate
  small PR).
- **`MarketplaceSettings.vue` (Settings → Plugin Marketplaces tab)**:
  stays as-is. Registry admin is a separate concern. If the audit's
  "possibly relocated" suggestion has legs, address in a follow-up.

## Sidebar changes (`AppSidebar.vue`)

- Add ONE new entry: "Marketplace" → `marketplace` route. Position:
  in the Forge section near Plugins / Skills / MCP Servers (the
  natural neighbors).
- Remove sidebar entries that pointed at the deleted Explore X
  pages (per the PR-B audit, ExploreMcpServers and ExploreSkills
  did have sidebar entries under their respective Forge sub-sections;
  ExplorePlugins similar). Verify in `AppSidebar.vue` and remove
  the right rows.
- **Update the `isXSectionActive` computed arrays.** Per codex
  pre-impl review, `AppSidebar.vue` has 4 active-state computeds +
  `sidebarActive()` array checks that reference the old explore
  route names (`explore-skills`, `explore-plugins`,
  `explore-mcp-servers`, `explore-super-agents`). After this PR
  those names still resolve (via the redirect entries) but the
  highlight logic should treat the new `marketplace` route as
  belonging to the right section. Add `marketplace` to each
  relevant `isXSectionActive` array (probably the Plugins, Skills,
  MCP Servers, and SuperAgents section arrays) so the section
  expands and highlights correctly when the operator is on the
  Marketplace page via any tab.

## Tests

- Update `frontend/src/components/layout/__tests__/AppSidebar.structure.test.ts`:
  - Forge no longer contains `explore-plugins`, `explore-skills`,
    `explore-mcp-servers`, `explore-super-agents` sidebar entries.
  - Forge contains a new `marketplace` sidebar entry.
- New `frontend/src/views/__tests__/MarketplacePage.test.ts`:
  - Mounts the page with each `?type=X` and asserts the right
    subcomponent mounts.
  - Defaults to `plugins` tab when no query param given.
  - Tab click updates the URL query param without re-mounting the
    whole page.
- Optional smoke tests for each subcomponent are nice-to-have but
  not required if the original Explore X tests still pass against
  the ported components.

## Risks + mitigations

1. **Per-type behavior preservation.** The audit identified
   per-type quirks (skills two-lane, mcp-servers typed install,
   super-agents stub). Mitigation: port to siblings rather than
   trying to unify into one list — each subcomponent owns its
   own quirks.
2. **MarketplaceSettings overlap.** The Settings registry-admin
   tab uses some of the same `marketplaceApi.*` calls as the
   browse pages. Mitigation: don't touch the admin tab; the
   browse pages and the admin tab can coexist on the same APIs.
3. **Orphan-route data loss.** `SkillMarketplacePage` is being
   deleted; its "installed+available join on one specific registry"
   view is unique. Mitigation: verify the same data is reachable
   from the admin tab's per-registry view; if not, port the join
   logic into `MarketplaceSkills.vue` as an optional "filter by
   registry" mode. Decide at impl time.
4. **WebMCP page tools.** Some tools may reference the removed
   routes by name. Mitigation: grep for `explore-plugins`,
   `explore-skills`, etc. across `frontend/src/webmcp/` before
   commit; fix any stale refs.
5. **Test infra.** The new structure test from PR-B asserts Forge
   contains specific items. Update those assertions in lockstep.

## Test plan

- [ ] `cd frontend && npx vue-tsc --noEmit` clean
- [ ] `cd frontend && npm run test:run` green (with updated sidebar
  test + new MarketplacePage test)
- [ ] `cd frontend && npm run build` green
- [ ] Manual: open the app, navigate to `/marketplace`, verify
  4 tabs render
- [ ] Manual: load `/plugins/explore` directly, verify redirect to
  `/marketplace?type=plugins`
- [ ] Manual: verify Settings → Plugin Marketplaces tab still works
  unchanged
- [ ] Manual: verify `BotTemplateMarketplace` (`/bot-templates`)
  still works unchanged

## Out of scope for PR-C

- Dashboards lanes (PR-D)
- Design wizards grouping (PR-D)
- On-Call Escalation move (PR-D)
- BotTemplateMarketplace relocation (follow-up)
- MarketplaceSettings relocation (follow-up)
- Registry admin redesign (follow-up)
