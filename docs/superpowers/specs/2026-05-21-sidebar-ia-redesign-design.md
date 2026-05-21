# Sidebar IA Redesign — Design

**Status:** Approved 2026-05-21
**Audit:** `.planning/sidebar-audit.md` (commit `2d22e15`) — 738-line per-surface
analysis of the 25+ sidebar entries.

## Problem

The left sidebar accumulated 25 top-level entries + many submenu items across
the v0.5.x–v0.7.x waves. The audit revealed the structure fights the domain
model rather than reflecting it:

- **Triggers is the central abstraction** (17 sidebar destinations are facets
  of the Trigger entity), but it's treated as a leaf under Forge.
- **"Integrations" is mislabeled** — only 3 of 9 entries are real integrations.
  The other 6 are PR-trigger facets, rotation domain, or trigger orchestration
  that landed there by accident.
- **Real same-component duplicates** exist: `security-history` + `audit-history`
  mount the same view; 4 "Explore X" pages + Settings's "Add Marketplace" tab
  rebuild the same marketplace registry UI.
- **6 design wizards** (agent / skill / command / hook / rule / plugin) share
  copy + pattern but aren't grouped.
- **~10 static-smell pages** with zero API calls in `<script setup>` —
  likely placeholders.
- **Activity pattern post-March 2026:** energy went into SuperAgents + design
  wizards + modal/UX hardening + Token Usage + AI Backends. Automation Tools
  + Integrations have only had TS-error-sweep commits since v0.5.x.

## Goal

Shrink the sidebar's cognitive load by making the IA reflect the domain model
the audit identified — not just by collapsing labels. Target: ~13 top-level
sections (from 25), with each section earning its slot by representing a
distinct domain concept the user reaches for.

Hard constraint: Agents ≠ SuperAgents (subagent vs persistent-session agent),
they stay separate.

## Approach

Four sequential PRs. Each goes through the standing codex-review-until-green
loop, plus an additional **plan-review pass** before implementation per
the user's instruction.

### PR-A — Trim & cut (pure subtraction)

**Goal:** delete redundant entries that don't earn their slot. Safest first
PR (no structural moves, mostly pure deletions).

Scope:
- Drop one of each same-component duplicate entry:
  - `security-history` (keep `audit-history` — both mount `AuditHistory.vue`)
  - `project-instance-playground` left in place since it's project-scoped;
    `super-agent-playground` left in place since it's SA-scoped (same
    component, two URL spaces, both legitimately reachable)
- Triage each of the 10 static-smell pages. For each: delete the route +
  sidebar entry + view file unless the page has a working backend behind it
  that we just haven't audited deeply enough. Static-smell list per audit:
  `team-leaderboard`, `execution-anomaly-detection`, `team-budgets`,
  `execution-quota-controls`, `report-digests`, `mobile-execution-monitor`,
  `bot-sla-uptime`, `system-errors`, `structured-output`, `bot-runbooks`.
- Verify removed pages have no inbound `router.push` from elsewhere.

### PR-B — Triggers promotion

**Goal:** make the IA reflect that Triggers is the central abstraction.

Scope:
- New top-level "Triggers" section.
- Pull trigger facets out of Forge / Integrations / Automation Tools into it:
  - From Forge: the existing `triggers` entry
  - From Integrations: PR Auto-Assignment, PR Review Learning Loop, GitHub
    Actions, Multi-Provider Fallback, Multi-Repo Fan-Out (all PR-trigger /
    orchestration facets per audit)
  - From Automation Tools: trigger-config pages (Inline Prompt Editor,
    Visual Cron Wizard, Conditional Trigger Rules, Repo Scope Filters,
    Structured Output, Prompt A/B Testing, Cross-Team Bot Sharing, Bot
    Clone & Fork, Incident Response Playbooks)
- Move On-Call Escalation under Scheduling (it's rotation domain, not
  integration).
- Slack + Ticketing + Notification Channels remain in a renamed "External
  Integrations" section (the 3 real integrations from the audit).

### PR-C — Marketplace consolidation

**Goal:** one Marketplace page replacing 5 separate "Explore X" pages.

Scope:
- New `MarketplacePage.vue` with type filters (plugins / skills / mcp-servers /
  super-agents).
- Delete `ExplorePluginsPage.vue`, `ExploreSkillsPage.vue`,
  `ExploreMcpServersPage.vue`, `ExploreSuperAgentsPage.vue`.
- Replace the Settings "Add Marketplace" tab with a router link to the new
  Marketplace page.
- One sidebar entry: "Marketplace" (replaces the 4 sidebar items).

### PR-D — Dashboards lanes + wizard grouping

**Goal:** 13 dashboards → 4 lane pages; 6 design wizards become a coherent
"Create" surface.

Dashboard lanes (from audit):
- **Quality:** Security Scan + PR Review + Anomaly Detection
- **Cost:** Token Usage
- **Health:** Health Monitor + Bot Health (audit confirmed these are the same
  concept with different APIs)
- **Activity:** Scheduling + Execution Queue + Impact Report + Cross-Team
  Insights + ROI Leaderboard

Each lane is a multi-card page composed of the existing dashboard components
under new wrapper views. Old routes (e.g. `/dashboards/bot-health`) redirect
to the new lane (e.g. `/dashboards/health`) so bookmarks survive.

Wizard grouping: the 6 design wizards (`agent-create`, `skill-create`,
`command-design`, `hook-design`, `rule-design`, `plugin-design`) become
discoverable from a single "Create" entry point on their respective list
pages OR as a unified surface — TBD in PR-D's plan-review pass.

## Out of scope

- Renaming SuperAgents (separate domain decision).
- Watch Tower / Sketch flat top-level entries (kept).
- The Agents (subagent) section structure (kept).
- The Organization section (Products / Projects / Teams kept).
- Mobile-specific layout work.

## Process per PR

Per user instruction, each PR goes through:

1. **Plan review:** draft the per-PR plan (sub-spec) → spawn codex to
   review the plan against the audit + the goal. Iterate until plan-clean.
2. **Implementation.**
3. **Verification:** the standing codex-review-until-green policy
   (`feedback_always_codex_review_until_green`). Iterate until clean.
4. **Merge.**
5. **Move to next PR.**

## References

- Audit: `.planning/sidebar-audit.md` (commit `2d22e15`)
- Domain map: section G of the audit
- Static-smell list: section F of the audit
- Triggers-as-central-abstraction: section B of the audit
