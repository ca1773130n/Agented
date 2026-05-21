# PR-B Plan — Triggers promotion + duplicate cuts + ShipOrCut tags

**Spec:** `docs/superpowers/specs/2026-05-21-sidebar-ia-redesign-design.md`
**Audit:** `.planning/sidebar-audit.md` (commit `2d22e15`)
**Triage:** `.planning/static-smell-triage.md` (commit `b75a084`)

**Plan-review history:**
- Pass 1: codex flagged 2 BLOCKERs + 7 MAJORs. Plan was missing 9
  audit-listed trigger facets, deferred On-Call Escalation against the
  parent spec, off-by-one on ShipOrCut count (6 vs 7), GitHub Actions
  misclassified.
- Pass 2: codex flagged 2 BLOCKERs. On-Call Escalation moved to
  Triggers Ops still contradicts parent spec ("under Scheduling");
  GitHub Actions moved to External Integrations also contradicts
  audit §C ("PR-trigger facet"). Plus narrative/table mismatch on
  bot-templates and bot-recommendation-engine block labels; missing
  keyboard/mobile/ARIA risk entries.

**Spec amendment for PR-B:** the parent spec scopes On-Call Escalation
under Scheduling in PR-B, but Scheduling is currently a dashboard
route, not a section. Creating a Scheduling section is PR-D's scope
(when the dashboards consolidate into lanes). Rather than build a
single-item Scheduling section in PR-B just for On-Call Escalation,
**PR-B leaves On-Call Escalation in place (External Integrations) and
PR-D moves it under the new Scheduling section** alongside the lane
consolidation. The parent spec's PR-B scope is amended in this PR.

## Goal

Make the IA reflect the audit's finding that Triggers is the central
abstraction (17 sidebar destinations are facets of the Trigger entity).
Also drop the one genuine duplicate sidebar entry (`security-history`)
and add ShipOrCut tracking markers to the **7 STUB-PROMOTE pages** so
they get attention or removal next quarter.

## Trigger-facet disposition table

Per codex pre-impl review, every audit-identified trigger facet gets
an explicit disposition. Audit §B identifies 17 destinations as
Trigger facets (excluding the dynamic per-trigger dashboards/history
rows which scale with user data and stay where they are).

| # | Route | Current home | Disposition in PR-B | Block under Triggers |
|---|-------|--------------|---------------------|---------------------|
|  1 | `triggers` | Forge | **MOVE** | Core |
|  2 | `bot-templates` | Automation Tools | **MOVE** | Core |
|  3 | `bot-clone-fork` | Automation Tools | **MOVE** | Core |
|  4 | `cross-team-bot-sharing` | Automation Tools | **MOVE** | Core |
|  5 | `incident-response-playbooks` | Automation Tools | **MOVE** | Core |
|  6 | `inline-prompt-editor` | Automation Tools | **MOVE** | Config |
|  7 | `visual-cron-wizard` | Automation Tools | **MOVE** | Config |
|  8 | `conditional-trigger-rules` | Automation Tools | **MOVE** | Config |
|  9 | `repo-scope-filters` | Automation Tools | **MOVE** | Config |
| 10 | `structured-output` | Automation Tools | **MOVE** | Config |
| 11 | `prompt-ab-testing` | Automation Tools | **MOVE** | Config |
| 12 | `multi-provider-fallback` | Integrations | **MOVE** | Config |
| 13 | `multi-repo-fan-out` | Integrations | **MOVE** | Config |
| 14 | `pr-auto-assignment` | Integrations | **MOVE** | PR-Review |
| 15 | `pr-review-learning-loop` | Integrations | **MOVE** | PR-Review |
| 16 | `github-actions` | Integrations | **MOVE** | PR-Review |
| 17 | `webhook-recorder` | History | **MOVE** | Ops |
| 18 | `dependency-impact-bot` | Automation Tools | **MOVE** | Ops |
| 19 | `bot-recommendation-engine` | Automation Tools | **MOVE** | Ops |
| 20 | `bot-dependency-graph` | Automation Tools | **MOVE** | Introspection |
| 21 | `bot-performance-benchmarks` | Automation Tools | **MOVE** | Introspection |
| 22 | `bot-runbooks` | Automation Tools | **MOVE** | Introspection |
| 23 | `execution-tagging` | Automation Tools | **MOVE** | Introspection |
| 24 | `changelog-generator` | Automation Tools | **MOVE** | Introspection |

Deferred entries:

| Route | Disposition | Rationale |
|-------|------------|-----------|
| `on-call-escalation` | **DEFER to PR-D** | Parent spec scopes it under Scheduling, but Scheduling is currently a dashboard route. PR-D creates the Scheduling section as part of dashboards-lane consolidation; on-call moves with it. **PR-B leaves on-call-escalation in External Integrations.** (Spec amendment noted above.) |

**Total moves:** 24 entries into Triggers. External Integrations stays
at its current 4 items (Slack, Ticketing, Notification Channels, On-Call
Escalation) pending PR-D.

## Sidebar structural changes (`frontend/src/components/layout/AppSidebar.vue`)

### New top-level `Triggers` section

24 sub-items grouped into 5 visual blocks. Block labels are
presentational only — the sidebar structure is flat under the
section heading.

**Block 1: Core (5)**
- Triggers (main list)
- Bot Templates
- Bot Clone & Fork
- Cross-Team Bot Sharing
- Incident Response Playbooks

**Block 2: Configuration (8)**
- Inline Prompt Editor
- Visual Cron Wizard
- Conditional Trigger Rules
- Repo Scope Filters
- Structured Output
- Prompt A/B Testing
- Multi-Provider Fallback
- Multi-Repo Fan-Out

**Block 3: PR-Review (3)**
- PR Auto-Assignment
- PR Review Learning Loop
- GitHub Actions

**Block 4: Ops (3)**
- Webhook Recorder
- Dependency Impact Bot
- Bot Recommendation Engine

**Block 5: Introspection (5)**
- Bot Dependency Graph
- Bot Performance Benchmarks
- Bot Runbooks
- Execution Tagging
- Changelog Generator

### Renamed `External Integrations` section (was `Integrations`)

Down from 9 entries to 4 (real integrations + on-call held until PR-D):
- Slack Integration
- Ticketing Integration
- Notification Channels
- On-Call Escalation (held — PR-D moves it under Scheduling section)

The other 5 displaced entries are absorbed into the new Triggers
section (rows 12–16 in the disposition table: multi-provider-fallback,
multi-repo-fan-out, pr-auto-assignment, pr-review-learning-loop,
github-actions).

### Removed entries from `Forge`

- `triggers` (moved to new Triggers section)

Forge keeps: Workflows, Plugins, MCP Servers, Skills, Commands, Hooks,
Rules.

### Removed entries from `Automation Tools`

All trigger facets per the disposition table (rows 2–11, 17–18, 19–23).
That leaves `Automation Tools` with: **Prompt Snippets** only.

**Decision:** since one item is too thin for a section, **fold Prompt
Snippets into the new Triggers section** under a 6th block "Authoring"
— OR keep Automation Tools as a single-item section until PR-C/D
renames it. Defer this micro-decision to the implementation: choose
whichever leaves fewer total sections.

### `security-history` sidebar entry deleted

The route + view stay (it's a thin wrapper that mounts
`AuditHistory.vue`). The sidebar entry under History → Triggers →
"Security Scan" is the duplicate. Users reach security history via
`audit-history` instead.

## Code-only changes

### ShipOrCut markers

For the **7** STUB-PROMOTE pages (per
`.planning/static-smell-triage.md`), add a marker comment at the top
of each `<script setup>` including the triage agent's per-page
backend assessment:

```ts
// ShipOrCut: 2026-Q3 — <triage agent's exact verdict + backend path or
// "no backend yet". See .planning/static-smell-triage.md>.
// Ship the feature or remove the route by EOQ3.
```

Pages (verdict from the triage file):
1. `frontend/src/views/TeamLeaderboardPage.vue` — backend stub in `app_litestar/routes/leaf_crud_d.py`
2. `frontend/src/views/ExecutionAnomalyDetection.vue` — backend stub
3. `frontend/src/views/ExecutionQuotaControls.vue` — backend stub
4. `frontend/src/views/ReportDigestsPage.vue` — backend stub
5. `frontend/src/views/BotSlaUptimePage.vue` — backend stub
6. `frontend/src/views/StructuredOutput.vue` — **no backend at all** (top of cut list)
7. `frontend/src/views/BotRunbooksPage.vue` — **no backend at all** (top of cut list)

## Routes (`frontend/src/router/routes/*.ts`)

No route renames — pure sidebar reorganization. Tests that grep on
route names stay green.

## WebMCP page tools

No changes needed (route names unchanged).

## Tests

Per the codex plan review, **there is no existing Vitest file that
asserts sidebar section labels or item membership**. `App.test.ts`
stubs out `AppSidebar`; `useSidebarCollapse.test.ts` covers only
collapsed/mobile state. So no existing tests break from the moves.

**New test**: add `frontend/src/components/layout/__tests__/AppSidebar.structure.test.ts`
asserting:
- The new "Triggers" section header exists.
- The "Triggers" section contains 24 sub-items.
- The "Integrations" section is renamed to "External Integrations"
  and contains exactly 4 items.
- The "Forge" section no longer contains a "Triggers" sub-item.
- The "Automation Tools" section no longer contains the displaced
  trigger-config sub-items.
- The "security-history" sidebar entry is absent (the route stays).

The test asserts presence/absence by data-testid or label text,
mounted with `vue-router` + the same fixture data the sidebar reads
in production.

## Risks + mitigations

1. **24 entries in one section is dense.** Mitigation: 5 visual
   blocks (Core / Configuration / PR-Review / Ops / Introspection)
   give the eye resting points. Block labels render as subtle
   non-clickable separators. Section default state is collapsed —
   users only see the 24 items when they expand Triggers.

2. **Automation Tools is left with 0 or 1 items.** Two options
   (decide at implementation time): (a) fold Prompt Snippets into
   Triggers under a 6th "Authoring" block; (b) keep Automation Tools
   as a single-item section. Pick whichever yields fewer total
   sections.

3. **On-Call Escalation is held in External Integrations until PR-D.**
   The parent spec scoped it under Scheduling in PR-B, but Scheduling
   is still a dashboard route. Creating a single-item Scheduling
   section in PR-B (just for On-Call Escalation) is wasted work
   when PR-D will build that section as part of dashboards-lane
   consolidation. PR-D moves on-call from External Integrations to
   the new Scheduling section in one step. The spec amendment at
   the top of this plan captures the scope change.

4. **Sidebar height when expanded** — the Triggers section will be
   the tallest by far. Mitigation: collapsed by default; the existing
   nav-submenu CSS already scrolls when overflowing the viewport.

5. **GitHub Actions stays in the Triggers section under PR-Review
   block.** Pass-2 codex review pointed out audit §C classifies it
   as a PR-trigger facet (not a real integration), so it goes into
   Triggers → PR-Review alongside PR Auto-Assignment + PR Review
   Learning Loop. (Pass 1 had it correctly in PR-Review; pass 2's
   move to External Integrations was a mistake that pass 3 reverts.)

6. **No existing sidebar-structure tests to break** (verified by
   codex plan review). The new test added in this PR (see below) is
   the first to assert section composition.

7. **Keyboard navigation through 24 items.** Tab order through the
   expanded Triggers section is long. Mitigation: each block label is
   non-focusable (`tabindex="-1"`); items remain individually
   focusable. Verify with a manual tab walk that focus moves
   block→items→next-block→items cleanly.

8. **Mobile collapse behavior.** On mobile the sidebar drawer
   collapses by default; expanding Triggers there shows 24 items in
   a narrow column. Mitigation: existing `useSidebarCollapse`
   composable handles overflow scrolling; verify on a small viewport.

9. **ARIA on visual-only block labels.** Block labels (Core /
   Configuration / PR-Review / Ops / Introspection) are presentational.
   Use `role="presentation"` and `aria-hidden="true"` to hide them
   from screen readers; the 24 items already have meaningful labels.
   Alternative: wrap each block in `<div role="group" aria-label="...">`
   to expose the structure to AT. **Decide at implementation:** start
   with `aria-hidden` (simpler) and only escalate to group roles if
   manual screen-reader testing shows the flat 24-item list is
   confusing.

## Test plan

- [ ] `cd frontend && npx vue-tsc --noEmit` clean
- [ ] `cd frontend && npm run test:run` green (with updated AppSidebar
  tests reflecting the new structure)
- [ ] `cd frontend && npm run build` green
- [ ] Manual: open the app, expand the new Triggers section, verify
  every link navigates to the expected page
- [ ] Manual: verify the External Integrations section shows only the
  3 real integrations
- [ ] Manual: verify Forge no longer shows Triggers and Automation
  Tools no longer shows the 9 displaced entries
- [ ] Manual: verify `security-history` is no longer a sidebar entry
  (its route still works via direct URL)

## Out of scope for PR-B

- Marketplace consolidation (PR-C)
- Dashboards lanes (PR-D)
- Design wizards grouping (PR-D)
- On-Call Escalation move (deferred to PR-D)
- Section reorder (PR-D or later)
- `Automation Tools` → `Authoring` rename (PR-C or PR-D)
