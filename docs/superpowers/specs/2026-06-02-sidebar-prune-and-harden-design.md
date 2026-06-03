# Sidebar Prune + Production-Hardening — Design Spec

**Date:** 2026-06-02
**Status:** Approved 2026-06-02. **Phase 1 (hard-cuts) complete & verified** —
commits `61242f6f` (frontend), `8808b5b8` (backend), `ffd4ccc4` (test stub) on
branch `prune/phase1-sidebar-hard-cuts`; frontend build + 1344 tests green,
backend 3358 passed (3 unrelated pre-existing failures). **P2 (merges +
relocations) and P3 (IA restructure) pending.**
**Owner:** Agented operator console (frontend `frontend/`, backend `backend/`)

## 1. Goal & locked decisions

The product has accreted **179 views, ~30 route groups, ~80 sidebar leaf links, and a
numbered feature-checklist** (`Feature 4…39`, plus 9 generic `leaf_crud_a–i` backend
modules). Two sidebar groups are grossly overloaded — **Forge → Triggers (21 items)** and
**System → Platform (13 items)** — and several "features" are non-functional (404 / 501 /
mock). This matches the repo's own recorded "PR-J2 garbage" episode and the principle:
**a working backend does not earn a sidebar slot; the test is "operator reaches it routinely,
or it is a domain entry-point."**

User decisions (locked):
- **Scope:** Prune, then harden.
- **Cut depth:** Menu + dead code (delete unreferenced view/route/backend/tests).
- **Quality bar:** Full — real wiring (no stubs/TODOs), loading + empty + error states,
  4-locale i18n parity (en/ko/ja/zh), green tests.

## 2. How the cut list was derived (evidence, not vibes)

1. **Mechanical scoring** of every sidebar-reachable view: LOC, stub/placeholder markers,
   real-API wiring, i18n coverage. (Used as a *signal*, with known noise — HTML
   `placeholder=` inflates "stub" counts; treated as starting point only.)
2. **4 parallel read-only investigators**, one per thematic cluster, verifying for each
   feature: backend reality (real / thin / mock-none), dependents (onboarding tour, tests,
   cross-imports, core-page links), and overlaps.
3. **Direct backend spot-verification** of every "broken" claim before authorizing deletion
   (results inline below).

Confidence legend: **[V]** = verified against source this session; **[A]** = investigator
evidence, re-confirm at execution.

## 3. Cut list

### A. HARD CUT — non-functional or pure-duplicate (delete view + route + slot + test)

| Route | View | Evidence | Backend |
|---|---|---|---|
| `bot-runbooks` | BotRunbooksPage.vue | **[V]** 0 backend refs; UI fetches nonexistent `/admin/bots/runbooks` (404) | none |
| `bot-sla-uptime` | BotSlaUptimePage.vue | **[V]** `misc.py:91` "Stub — not yet tracked"; overlaps real `bot-health` | remove stub handler |
| `execution-quota-controls` | ExecutionQuotaControls.vue | **[V]** `executions.py:489/501` mutations return 501; GET `{rules:[]}` | remove stub handlers |
| `report-digests` | ReportDigestsPage.vue | **[A]** GET `[]`, POST/PUT 501 ("UI was lying about Saved"); test asserts empty-state only | remove stub + test |
| `mobile-execution-monitor` | MobileExecutionMonitor.vue | **[A]** responsive duplicate of Activity lane | none (reuses `/executions`) |
| `dependency-impact-bot` | DependencyImpactBot.vue | **[A]** fabricates "impact" client-side from unrelated trigger fail-rates; no backend | none |
| `webhook-recorder` | WebhookRecorder.vue | **[A]** relabels Executions; stores nothing | none (reuses) |
| `provider-benchmark-dashboard` | ProviderBenchmarkDashboard.vue | **[V]** no benchmark backend; fakes latency from account cooldown; dup of AI-Backends health | none |
| `bot-clone-fork` | BotCloneForkPage.vue | **[A]** "clone" = create-with-prefill; no fork semantics | none |
| `cross-team-bot-sharing` | CrossTeamBotSharing.vue | **[A]** read-only grouped view; no sharing persistence | none |
| `incident-response-playbooks` | IncidentResponsePlaybooks*.vue | **[A]** re-skin of bot-templates + hardcoded fallbacks | none (reuses `botTemplateApi`) |
| `inline-prompt-editor` | InlinePromptEditor.vue | **[A]** single-field editor for `trigger.prompt_template`, already on trigger detail | none (reuses) |

### B. CUT slot now, retire backend in a follow-up PR

| Route | View | Note |
|---|---|---|
| `bot-output-piping` | BotOutputPipingPage.vue | Real `bot_pipes` table (14 refs) but niche bot→bot power-toy. Remove slot+view now; retire `bot_pipes` table/routes separately to avoid a risky data migration in the prune PR. |

### C. MERGE → fold into a parent surface (remove standalone slot, KEEP backend, port useful UI)

| Route | Folds into | Why |
|---|---|---|
| `nl-trigger-rule-editor` | `conditional-trigger-rules` | Same `triggerConditionsApi` + `trigger_conditions` table; NL "compile" is a brittle `.includes(' or ')` heuristic → becomes an input mode. |
| `bot-output-webhook-forwarding` | Integrations | It is the Integrations surface filtered to webhooks. |
| `slack-notifications` | Integrations (`notification-channels`) | One `db_integrations` table, `type=slack`. |
| `integration-ticketing` | Integrations (`notification-channels`) | Same table, `type=jira/linear`. |
| `execution-search` | Executions / Activity | Should be a filter on the executions list, not a sibling. |
| `execution-tagging` | Executions / Activity | Tagging belongs on the executions list; keep `execution_tags` backend. |
| `visual-cron-wizard` | Trigger schedule editor | Fold the cron-builder into the trigger/schedule form; keep `validate_cron_expression`. |
| `skill-version-pinning` | Skills detail | Real `version_pins` backend (13 refs); niche → fold into skills. |
| `conversation-history-viewer` | Agent detail | Renders an existing agent-creation conversation; not a destination. |
| `github-actions` | GitHub setup / onboarding (Help) | Static copy-paste YAML snippet; real ingest stays in `webhooks.py`. **[resolved: relocate]** |
| `plugin-sdk` | Help / Docs area | Static SDK reference + scaffold; relocate, not a top-level slot. **[resolved: relocate]** |
| `ai-cost-dashboard` | `dashboards-cost` lane | Fold the AI-spend view into the Cost lane; one cost surface. **[resolved: merge]** |

### D. KEEP-RELOCATE → action on a parent object (remove top-level slot, keep backend)

| Route | Relocates to | Why |
|---|---|---|
| `bot-dry-run` | Trigger detail (pre-flight action) | Real `dry_run` backend; it's an action, not a page. |
| `webhook-payload-transformer` | Trigger config (inline) | **[V]** real `payload_transformers.py`; trigger-scoped. |
| `execution-replay-diff` | Execution detail (action) | Real `ReplayService`. |
| `execution-annotation` | Activity / Quality lane | **LOAD-BEARING** — Life-Harness annotation/eval loop (`session_annotations`, 13 refs). Relocate; never delete backend. |
| `pr-auto-assignment` | "PR Automation" subgroup (Triggers) | Real `pr_assignment` backend. |
| `pr-review-learning-loop` | "PR Automation" subgroup (Triggers) | Real `PrReviewService`. |

### E. KEEP (survivors / domain entry-points / load-bearing)

`conditional-trigger-rules` (rule-editor survivor), `prompt-snippets` (consumed by prompt
rendering — load-bearing), `bot-templates` (real deploy path), `traces-list` (observability,
tested), `notification-channels` (merged Integrations home), `harness-integration` (core
harness wiring) — plus all Tier-0 core: dashboards + lanes, sketch, products, projects,
teams, agents, super-agents, workflows, plugins, skills, mcps, commands, hooks, rules,
settings, secrets-vault, rbac, sso, api-keys, system-errors, audit-history, usage-history,
findings-triage, ai-backends, marketplace.

**Net effect:** ~30 sidebar slots removed or folded. Triggers 21 → ~5; Platform 13 → ~7;
Integrations 3 → 1.

## 4. Target sidebar IA (after)

```
WORK            Dashboards (Quality/Cost/Health/Activity) · Sketch
ORGANIZATION    Products · Projects · Teams · Agents · Super-Agents
FORGE           Workflows
                Triggers ▸ Triggers · Conditions · Bot Templates ·
                          PR Automation ▸ Auto-Assign · Learning Loop · Prompt Snippets
                Plugins · MCPs · Skills · Commands · Hooks · Rules · Marketplace
OBSERVABILITY   Executions (search/tag filters; replay/annotate actions) · Traces ·
                AI Cost · Audit Log · Usage · System Errors · Findings Triage
PLATFORM        AI Backends · Integrations (Slack/Ticketing/Channels tabs) ·
                Harness Integration · Secrets · RBAC · SSO · API Keys · Team Budgets · Settings
```

## 5. Execution plan

**Recommended approach: phased branches, each codex-reviewed-until-green then 3-gate verified.**

- **Phase 1 — Hard-cuts (§A + §B).** Delete views/routes/slots/tests for the 14 non-functional
  or duplicate features; remove the dead stub backend handlers (`misc.py` SLA, `executions.py`
  quota, digests). Fast, low-risk, removes broken junk. Per-removal safety: grep all references
  → `just build` → `pytest` → `npm run test:run`.
- **Phase 2 — Merges & relocations (§C + §D).** Port useful UI into parent surfaces; collapse
  the Integrations trio into tabs; add the "PR Automation" subgroup; fold conditions/cron/version-
  pinning/annotation/replay into their domains. Update `AppSidebar.vue`, route files,
  `AppSidebar.structure.test.ts`, and i18n catalogs.
- **Phase 3 — IA restructure.** Apply the §4 section layout; collapse redirect-only routes.
- **Phases H1–H4 — Hardening waves to the full bar** (Organization → Forge → Observability →
  Platform): per surface, eliminate stubs/TODOs; add loading + empty + error states; bring all
  four locales to parity; green tests. Relocated capabilities are hardened where they land.

Alternatives considered: **per-domain vertical slices** (cohesive but sidebar churns repeatedly,
broken features linger) and **big-bang single PR** (fastest to "done" but unreviewable, risky).
Rejected in favor of the phased approach.

## 6. Verification protocol (every phase)

CLAUDE.md three-gate, all must pass: `just build` (vue-tsc + vite) · `cd backend && uv run pytest`
· `cd frontend && npm run test:run`. Each deletion is preceded by a reference sweep
(`grep -rn <route-name>\|<ViewName>` across `frontend/src` + `backend`) to confirm nothing
load-bearing breaks. PRs reviewed via `codex:codex-rescue` until clean, then merged.

## 7. Risks & rollback

- **False-positive cut:** mitigated by per-removal reference sweep + the three-gate + cut depth
  starting at the *verified-broken* set.
- **i18n drift:** all four locale catalogs edited in the same change (key-identical).
- **Backend table retirement** (`bot_pipes`, etc.) deferred to follow-ups to avoid data
  migrations inside the prune.
- Rollback = revert the phase branch; nothing is force-pushed.

## 8. Decisions (resolved 2026-06-02)

1. **AI-Cost → merge** into the `dashboards-cost` lane (single cost surface).
2. **`plugin-sdk` / `github-actions` → relocate** to a Help/Docs/Onboarding area (not top-level slots).
3. **Sequencing → full prune**: run P1 (hard-cuts) → P2 (merges + relocations) → P3 (IA restructure)
   as a sequence of reviewed PRs *before* the H1–H4 hardening waves.

## 9. Out of scope (follow-ups)

Backend table retirement for `bot_pipes`; the 9 `leaf_crud_a–i` consolidation; deeper backend
service audit; a Korean `*.ko.md` sibling of this spec (added once the cut list is approved, to
avoid translating a draft that will change).
