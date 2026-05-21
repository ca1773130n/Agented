# Marketplace audit — input for PR-C planning

**Date:** 2026-05-22
**Branch:** `fix/tour-prefetch-flake` (audit only; commit on `main`).
**Purpose:** map every marketplace-adjacent surface (frontend view + route +
backend endpoint) so PR-C of the sidebar IA redesign can be planned against
the real codebase, not the parent spec's "4 + 1" simplification.

---

## TL;DR

- The parent spec calls out **5 surfaces** (4 Explore X + Settings "Add
  Marketplace") to fold into one Marketplace page. The reality is **7
  distinct surfaces** plus a shared registry-config tab.
- The 4 "Explore X" pages are **not the same UI** — they share patterns
  (search box, card grid, modal install) but their **install actions and
  data sources diverge sharply**:
  - `ExplorePlugins` → marketplace search + `pluginExportApi.importFromMarketplace`.
  - `ExploreSkills` → marketplace search **and** `skillsShApi` (skills.sh
    external registry, npx-based install).
  - `ExploreMcpServers` → marketplace search → `mcpServerApi.create` with a
    typed install form (stdio/url/env/args/timeout).
  - `ExploreSuperAgents` → marketplace search only; **install is stubbed**
    (`"SuperAgent import coming in a future update"`).
- `SkillMarketplacePage.vue` (`/skills/marketplace`) is a **second skills
  marketplace UI**, not a duplicate of `ExploreSkills` — it's a unified
  installed-vs-available list pinned to one selected registry; it does
  **not** integrate skills.sh.
- `BotTemplateMarketplace.vue` is **not a marketplace at all** — it browses
  built-in `BotTemplate` records (DB-seeded) and a NL Bot Creator that streams
  trigger config generation. Install = `botTemplateApi.deploy(id)` which
  instantiates a trigger, not "install a package". This is closer to the
  Workflows / templates concept than to plugin install.
- The Settings "Add Marketplace" tab is `MarketplaceSettings.vue`. It is a
  **registry config + plugin install panel**, not a marketplace browse page
  — it owns `marketplaceApi` CRUD (add/edit/delete registries), test
  connection, deploy-to-marketplace, and per-registry plugin install. It is
  the *administration* surface that all Explore X pages talk back to via
  `marketplaceApi`.

So the parent spec's "4 + 1 → 1" framing is **partially wrong**:
- The "1 Marketplace page" assumption is sound for `ExplorePlugins`,
  `ExploreSkills`, `ExploreMcpServers`, and probably the SaaS-side of
  `SkillMarketplacePage`.
- `ExploreSuperAgents` is essentially **stub UI** with no install path —
  consolidating it is free but won't reduce real functionality.
- `BotTemplateMarketplace` is a **different consumption model** (clone-to-
  instantiate, not install). Folding it into the same page misleads users.
- The Settings tab is **registry administration** with deploy/export
  workflows. A naive "router link to /marketplace" loses test-connection,
  deploy, refresh, watch, sync-status, and the destructive delete flows.

Recommended re-framing: **"5 browse pages + 1 admin tab → 1 browse page +
1 admin surface"**, with `BotTemplateMarketplace` treated as a Triggers/
Workflows artifact (not marketplace), and the Settings tab kept as the
"Marketplaces" administration view (possibly relocated, but not deleted).

---

## Surface inventory

### Frontend view files

| # | View | Route | Sidebar entry | Last commit | Date |
|---|------|-------|---------------|-------------|------|
| 1 | `ExplorePlugins.vue` | `/plugins/explore` (`explore-plugins`) | Plugins → Explore | `6461fd5` | 2026-03-20 |
| 2 | `ExploreSkills.vue` | `/skills/explore` (`explore-skills`) | Skills → Explore | `d8d737f` | 2026-03-16 |
| 3 | `ExploreMcpServers.vue` | `/mcp-servers/explore` (`explore-mcp-servers`) | MCP Servers → Explore | `d8d737f` | 2026-03-16 |
| 4 | `ExploreSuperAgents.vue` | `/super-agents/explore` (`explore-super-agents`) | SuperAgents → Explore | `b2cba61` | 2026-03-06 |
| 5 | `BotTemplateMarketplace.vue` | `/bot-templates` (triggers routes) | none found in `AppSidebar.vue` | `302bd87` | 2026-03-05 |
| 6 | `SkillMarketplacePage.vue` | `/skills/marketplace` (`skill-marketplace`) | none found in `AppSidebar.vue` | `bba509e` | 2026-03-19 |
| 7 | `MarketplaceSettings.vue` (Settings tab) | `#marketplaces` on `/settings` | indirect (Settings) | `f5518f5` | 2026-05-10 |

Plus the bonus 8th surface noticed during the audit:

| 8 | `AgentSkillDiscoveryPage.vue` | `/agents/skill-discovery` | none found | `bba509e` | 2026-03-19 |

`AgentSkillDiscoveryPage` uses `skillsApi.discover` / `agentApi` to recommend
skills to an *agent* — discovery, not marketplace. Not a marketplace surface;
called out so it's not accidentally swept in.

---

### Per-surface audit

#### 1. `frontend/src/views/ExplorePlugins.vue`

- **IS:** marketplace browse for plugins.
- **SHOWS:** search box (debounced), grid of `MarketplaceSearchResult`
  cards across all configured registries, detail modal with install button,
  "Add Marketplace" modal (registry CRUD shortcut).
- **APIs:** `marketplaceApi.list`, `marketplaceApi.search(q, 'plugin')`,
  `marketplaceApi.refreshCache`, `marketplaceApi.create` (inline add),
  `pluginExportApi.importFromMarketplace`.
- **Backend:** `GET /admin/marketplaces`, `GET /admin/marketplaces/search`,
  `POST /admin/marketplaces/search/refresh`, `POST /admin/marketplaces`,
  `POST /admin/plugin-exports/import-from-marketplace`.
- **Data:** registries are local SQLite (DB); plugin metadata is fetched
  *live* per-registry by `DeployService.discover_available_plugins_cached`
  (so: federated remote registries surfaced through local DB list).
- **Inbound:** sidebar Plugins → Explore (button), `/plugins/explore` deep
  link.
- **WebMcp tool:** `agented_explore_plugins_get_state`.

#### 2. `frontend/src/views/ExploreSkills.vue`

- **IS:** marketplace browse for skills + skills.sh registry.
- **SHOWS:** search box, **two separate result lanes** — marketplace search
  results and `skillsShApi` results (with `npx_available` flag); add-
  marketplace modal.
- **APIs:** `marketplaceApi.list`, `marketplaceApi.search(q, 'skill')`,
  `marketplaceApi.create`, `skillsShApi.search`, `skillsShApi.install`,
  `userSkillsApi.add`.
- **Backend:** marketplace endpoints (as above with `type=skill`) +
  `GET /api/skills/skills-sh/search`, `POST /api/skills/skills-sh/install`,
  `POST /api/skills/user`.
- **Data:** local registries + external skills.sh (npx-installed packages).
- **Inbound:** sidebar Skills → Explore.
- **WebMcp tool:** `agented_explore_skills_get_state`.

#### 3. `frontend/src/views/ExploreMcpServers.vue`

- **IS:** marketplace browse for MCP servers.
- **SHOWS:** search + cards + install modal with typed form
  (`server_type: stdio|sse|http`, `command`, `args`, `url`, `env_json`,
  `timeout_ms`).
- **APIs:** `marketplaceApi.list`, `marketplaceApi.search(q, ...)`,
  `marketplaceApi.create`, `mcpServerApi.create`.
- **Backend:** marketplace endpoints + `POST /admin/mcp-servers`.
- **Data:** registries (local DB) → install creates an `mcp_servers` row.
- **Inbound:** sidebar MCP Servers → Explore.
- **WebMcp tool:** `agented_explore_mcp_servers_get_state`.

#### 4. `frontend/src/views/ExploreSuperAgents.vue`

- **IS:** marketplace browse for SuperAgent packages.
- **SHOWS:** search + cards + detail modal with an "Import" button that
  shows the toast `"SuperAgent import coming in a future update"` —
  install path is **stubbed**.
- **APIs:** `marketplaceApi` only (no install API yet).
- **Backend:** marketplace endpoints; no SuperAgent import endpoint.
- **Data:** registries.
- **Inbound:** sidebar SuperAgents → Explore.
- **WebMcp tool:** `agented_explore_super_agents_get_state`.

#### 5. `frontend/src/views/BotTemplateMarketplace.vue`

- **IS:** *not* a marketplace. Bot Template gallery + NL Bot Creator.
- **SHOWS:** grid of `BotTemplate` cards from local DB; **deploy** button
  instantiates the template (creates a trigger); separate panel with
  freeform description → SSE stream from `/admin/triggers/generate/stream`
  that materializes a `generatedConfig`.
- **APIs:** `botTemplateApi.list`, `botTemplateApi.deploy(id)`,
  `triggerApi`, raw `fetch(POST /admin/triggers/generate/stream)`.
- **Backend:** `GET /admin/bot-templates`, `GET /admin/bot-templates/{id}`,
  `POST /admin/bot-templates/{id}/deploy`, `POST /admin/triggers/generate/stream`.
- **Data:** local DB only (built-in templates, no remote registry).
- **Inbound:** Triggers routes file (`/bot-templates`); **not** present in
  `AppSidebar.vue` — likely orphaned route, reachable only by direct URL or
  from a Triggers screen.
- **Last commit:** 2026-03-05 — untouched since initial wave 09-03.

**Consumption model:** clone-to-instantiate (deploy = create a Trigger
record from the template), not install-a-package. Operates on local
records, has no marketplaceApi dependency.

#### 6. `frontend/src/views/SkillMarketplacePage.vue`

- **IS:** alternate skills marketplace view, scoped to one selected
  registry.
- **SHOWS:** dropdown to pick a registry, then a unified list merging
  *installed* (`marketplaceApi.listPlugins`) with *available*
  (`marketplaceApi.discoverPlugins`) — sort by name or installed status,
  install per row.
- **APIs:** `marketplaceApi.list`, `marketplaceApi.listPlugins`,
  `marketplaceApi.discoverPlugins`, `marketplaceApi.installPlugin`.
- **Backend:** `GET /admin/marketplaces`,
  `GET /admin/marketplaces/{id}/plugins`,
  `GET /admin/marketplaces/{id}/plugins/available`,
  `POST /admin/marketplaces/{id}/plugins`.
- **Data:** purely registry-driven (no skills.sh — diverges from
  `ExploreSkills`).
- **Inbound:** route exists (`/skills/marketplace`, name
  `skill-marketplace`) but **no sidebar entry** found in `AppSidebar.vue`.
  Likely reachable only via deep link or older nav.
- **Last commit:** 2026-03-19 — TS-error sweep, no feature work since.

**Why distinct from ExploreSkills:** different data joining strategy
(installed + available merged on one registry, vs. cross-registry search)
and **no skills.sh integration**. Title in nav also uses
`/admin/marketplaces/{id}/plugins` even for skills — appears to confuse
the plugin and skill artifact types, treating them as the same registry
row type (`MarketplacePlugin`). This is a smell.

#### 7. `frontend/src/components/settings/MarketplaceSettings.vue` (Settings → "Plugin Marketplaces" tab)

- **IS:** registry administration + per-registry plugin install/deploy.
- **SHOWS:** list of registered marketplaces with actions: select,
  test-connection, refresh (cache + discover), toggle deploy form, delete;
  per-marketplace inline deploy form (`plugin_id`, `version`); discovered
  available plugins with per-plugin install button.
- **APIs:** `marketplaceApi.list/create/update/delete`,
  `marketplaceApi.listPlugins/discoverPlugins`,
  `pluginApi.list` (local), `pluginExportApi.testConnection`,
  `pluginExportApi.deploy`, `pluginExportApi.importFromMarketplace`.
- **Backend:** all `/admin/marketplaces/*` (11 endpoints) +
  `/admin/plugin-exports/{test-connection,deploy,import-from-marketplace}`.
- **Data:** local DB (registries) + live discovery against each registry.
- **Inbound:** `/settings#marketplaces` tab — exposed by `SettingsPage.vue`
  alongside General, Security, Harness, MCP, GRD.
- **Tab label in UI:** "Plugin Marketplaces" (not "Add Marketplace"). The
  "Add Marketplace" thing the parent spec mentions is one **modal/button**
  inside this tab, plus the same inline-add modal present in each Explore X
  page. There is no standalone "Add Marketplace" page.
- **Last commit:** 2026-05-10 — actively maintained (most recent of the
  set; date-format migration wave).

---

### Backend endpoints (single map)

#### `/admin/marketplaces/*` (`leaf_crud_b.py`, mounted as
`marketplace_router`) — 11 endpoints

- `GET /` list, `POST /` create, `GET /search` cross-registry search,
  `POST /search/refresh` cache flush,
  `GET /{id}`, `PUT /{id}`, `DELETE /{id}`,
  `GET /{id}/plugins` installed list,
  `POST /{id}/plugins` install (`add_marketplace_plugin`),
  `DELETE /{id}/plugins/{pluginId}` uninstall,
  `GET /{id}/plugins/available` discover (live walk of registry).

#### `/admin/plugin-exports/*` (`leaf_crud_g.py`) — export/import bridge

- `POST /export`, `POST /import`, `POST /import-from-marketplace`,
  `POST /deploy`, `POST /test-connection`, `GET /{pluginId}/exports`,
  `POST /sync`, `POST /sync/entity`, `POST /watch`,
  `GET /{pluginId}/sync-status`.

#### `/admin/bot-templates/*` (`bot_templates.py`)

- `GET /`, `GET /{id}`, `POST /{id}/deploy`. (3 endpoints; no registry,
  no remote source.)

#### `/api/skills/*` (`skills.py`) — relevant subset

- `POST /harness/load-from-marketplace`,
  `POST /harness/deploy-to-marketplace`,
  `GET /skills-sh/search`, `POST /skills-sh/install`,
  `POST /user`, `GET /user`, ...

#### `/admin/mcp-servers/*` (consumed by `ExploreMcpServers.installPlugin`
→ `mcpServerApi.create`) — separate router family.

---

### Frontend API objects in play

- `marketplaceApi` (`services/api/marketplace.ts`) — registry CRUD,
  per-registry plugin operations, cross-registry search.
- `pluginExportApi` (`services/api/plugins.ts`) — install/deploy/sync
  bridge between local plugin records and remote registries.
- `skillsShApi` (`services/api/skills.ts`) — external skills.sh registry.
- `userSkillsApi` (`services/api/skills.ts`) — local skill records.
- `mcpServerApi` — local MCP server CRUD.
- `botTemplateApi` (`services/api/bot-templates.ts`) — list/get/deploy
  built-in templates.
- `triggerApi` — used by `BotTemplateMarketplace` for the generated config
  path.

---

## Consolidation reading

### Q1. Are the 4 Explore X pages truly the same UI?

**No — same skeleton, different verbs.** All four pages use the same
shell (PageHeader + search + grid + detail modal + add-marketplace
modal). But the action layer per artifact type diverges:

| Page | Search | Install path | Extra data source |
|------|--------|--------------|-------------------|
| Plugins | `marketplaceApi.search(q, 'plugin')` | `pluginExportApi.importFromMarketplace` | — |
| Skills | `marketplaceApi.search(q, 'skill')` + `skillsShApi.search` | `skillsShApi.install` (npx) or marketplace import | **skills.sh** |
| MCP servers | `marketplaceApi.search(q, ...)` | `mcpServerApi.create` (typed form) | — |
| SuperAgents | `marketplaceApi.search(q, ...)` | **stub** ("coming soon") | — |

A unified Marketplace page with a type filter is feasible, but it must
preserve:
- Two-lane results layout when type=skill (marketplace + skills.sh).
- Typed install form when type=mcp-server.
- A friendly "import not yet available" state when type=super-agent (or
  feature-gate it out of the type tabs until install lands).

### Q2. How do `BotTemplateMarketplace.vue` and `SkillMarketplacePage.vue` relate to the corresponding Explore X pages?

- `SkillMarketplacePage` vs `ExploreSkills`: **distinct**. Different
  data-join strategy (installed+available on one registry vs cross-registry
  search) and different external integrations (no skills.sh). It is the
  weaker of the two — feature-overlap with `ExploreSkills`, weaker
  inbound discovery (no sidebar entry). **Candidate for deletion** in
  PR-C, folding its registry-scoped view into the unified page as a
  "filter by registry" affordance.
- `BotTemplateMarketplace` vs `ExploreSuperAgents` / others: **distinct
  and unrelated**. It manages local `BotTemplate` records (no
  `marketplaceApi`, no remote registry) and houses the NL Bot Creator
  trigger-generation stream. It's a **Triggers/Workflows** artifact, not a
  marketplace package. **Do not fold into the unified Marketplace page.**

### Q3. What is the Settings "Add Marketplace" tab?

It is `Settings → Plugin Marketplaces` (`MarketplaceSettings.vue`), and
it is **not just an "add" form** — it is full registry administration:
add/edit/delete, test connection, refresh cache, deploy plugins to a
registry, install discovered plugins from a registry, with
`pluginExportApi` workflows attached. Replacing it with a router link is
**not equivalent** — the new Marketplace page needs to absorb (or keep
within reach of) these admin verbs:

- Add/edit/delete registry.
- Test connection per registry.
- Refresh discovery cache (per registry + global).
- Deploy plugin to registry (publish flow).
- Install discovered plugin from registry.
- Watch/sync per-plugin local dir mirroring (`pluginExportApi.toggleWatch`,
  `pluginExportApi.sync`).

Options:
- (a) Keep the Settings tab and have the unified Marketplace page link to
  it for "Manage registries…".
- (b) Move all of it into the Marketplace page as a sidebar/drawer
  "Registries" panel.
- (c) Split: cheap "Add Marketplace" inline on the Marketplace page;
  destructive/admin operations remain in Settings.

### Q4. What artifact types SHOULD the unified Marketplace page support?

- **Yes:** plugins, skills, mcp-servers (the three with real install paths).
- **Conditional:** super-agents — only when an install path exists; today
  it is stub UI. Either ship the type filter pre-disabled with a "coming
  soon" empty state, or omit until install lands.
- **No:** bot-templates — different consumption model (clone-instantiate
  via `botTemplateApi.deploy`, no remote registry). Leave under Triggers /
  Workflows. If sidebar discovery is the issue, surface a "Bot templates"
  link there, not under Marketplace.
- **No:** skill discovery for agents (`AgentSkillDiscoveryPage`) — that's
  a recommendation engine, not a marketplace.

---

## Surprises worth flagging

1. **`BotTemplateMarketplace` has no sidebar entry.** Route exists at
   `/bot-templates` (Triggers routes file), but `AppSidebar.vue` never
   navigates there. Either intentionally orphaned or a missing nav item
   from wave 09-03. Worth raising in PR-D (sidebar) regardless of PR-C.
2. **`SkillMarketplacePage` also has no sidebar entry.** Same situation.
3. **`ExploreSuperAgents.importPackage` is a toast stub.** Live in the
   product since 2026-03-06 with no install backend — three months of
   theater. PR-C is a natural moment to either retire it or ship the
   missing backend.
4. **Two skill marketplaces both alive** (`ExploreSkills` and
   `SkillMarketplacePage`) doing different things, with overlap. The
   parent spec's "delete `ExploreSkillsPage.vue`" wording is fine but
   doesn't mention `SkillMarketplacePage` at all.
5. **`MarketplaceSettings.vue` is the most-recently touched** of the set
   (2026-05-10) — operators clearly use the admin tab. Treat it as the
   load-bearing surface, not the disposable one.
6. **`AgentSkillDiscoveryPage` is unrelated** but lives under the same
   `skills/agents` mental cluster — call it out to prevent accidental
   sweep.
7. **`MarketplacePlugin` type is overloaded** — `SkillMarketplacePage`
   treats skills as `MarketplacePlugin` rows. The backend
   `/admin/marketplaces/{id}/plugins` endpoint returns plugins regardless
   of declared artifact type; there's no `/admin/marketplaces/{id}/skills`.
   So today the registry is plugin-centric, with skills/mcp/super-agents
   piggybacking on `MarketplaceSearchResult.search?type=...`. PR-C should
   decide whether to keep this single-type registry model or extend the
   backend.

---

## Re-framing of the parent spec

Parent spec said: **"4 Explore X pages + Settings's Add Marketplace tab → 1
Marketplace page"** (5 → 1).

True picture for planning: **5 browse-style pages + 1 admin tab → 1 browse
page + 1 admin surface**, where:

- The 5 browse pages are: `ExplorePlugins`, `ExploreSkills`,
  `ExploreMcpServers`, `ExploreSuperAgents`, `SkillMarketplacePage`.
- The 1 admin tab is `MarketplaceSettings` (kept, possibly relocated).
- `BotTemplateMarketplace` is **out of scope** for PR-C (it's a Triggers
  surface).
- The new page must preserve: skills.sh dual-lane, MCP typed install form,
  super-agent stub messaging, registry CRUD entry point, per-registry
  filter (from `SkillMarketplacePage`).
