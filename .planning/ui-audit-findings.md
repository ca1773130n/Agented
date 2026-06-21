# Agented UI-Audit Findings — Prioritized Report

Branch: `fix/ui-audit-sweep` · Generated: 2026-06-22 · Scope: Vue 3 + TS frontend (`frontend/src`)

Honors `CLAUDE.md`: no hardcoded user-facing strings (route through vue-i18n), 4-locale parity (en/ko/ja/zh, key-identical), CodeGraph/grep used to locate code. Findings that recur across pages via shared components are **collapsed to one entry** listing every affected file.

---

## Summary

### Counts by severity

| Severity | Count |
|---|---|
| High | 6 |
| Medium | 29 |
| Low | 29 |
| **Total** | **64** |

(Total reflects de-duplicated findings: the recurring `modal-close` / `&times;` icon-only-button a11y issue is collapsed into one shared finding **L1** that lists ~11 affected files, plus the distinct Marketplace ×-close variants at **M13**. The 64 entries cover all confirmed findings after collapsing those shared-component repeats.)

### Counts by category

Primary category per finding (slash-tagged findings — e.g. "bug/i18n" — counted by their primary category; the second tag is noted in-line).

| Category | Count |
|---|---|
| a11y | 23 |
| i18n | 19 |
| dead-control | 8 |
| bug | 7 |
| mock-data | 3 |
| redundancy | 3 |
| missing-state | 1 |

### Counts by risk tag

| Risk | Count |
|---|---|
| SAFE-MECHANICAL (auto-fixable) | 50 |
| NEEDS-VISUAL-CHECK (browser-verify first) | 14 |

---

# SAFE-MECHANICAL (auto-fixable)

These are deterministic edits — add an `aria-label`, route a literal through `t()`, drop a fabricated fallback array, fix an escaping bug. No browser verification required, but i18n changes must add the new keys **key-identical across en/ko/ja/zh**.

## HIGH

### H1 · mock-data · AnomalyDetectionCard injects fabricated anomalies on any non-501 error
- **Page:** dashboard
- **File:** `frontend/src/views/dashboards/cards/AnomalyDetectionCard.vue:85`
- **Evidence:** non-501 catch branch sets `anomalies.value = [{ id:'an-1', bot_name:'Security Audit', description:'Execution took 4x longer than baseline…', baseline_value:62, observed_value:248 }, …]` and `baselines.value = [{ bot_name:'Security Audit', avg_duration_s:62 }]` — a user reads fabricated "Security Audit"/"PR Review" rows as real anomalies.
- **Fix:** Remove the demo-data fallback (lines 85–95). On any error set `anomalies`/`baselines` to `[]` and surface an error+retry state the same way the 501 path shows `NotEnabledBanner`.
- **Risk:** safe-mechanical

### H2 · mock-data · RoiLeaderboardCard renders 5 fake teams as a real leaderboard on fetch error
- **Page:** dashboard
- **File:** `frontend/src/views/dashboards/cards/RoiLeaderboardCard.vue:40`
- **Evidence:** catch sets `teams.value = [{ rank:1, team_name:'Platform', total_executions:2341, success_rate:97.2, cost_saved_hrs:28, score:9820 }, …4 more]`. Backend already returns a `{teams:[]}` stub (line 6 "STUB-PROMOTE"), so the empty path is the truthful state.
- **Fix:** Drop the demo-team fallback (lines 40–46); set `teams.value = []` so the existing `EmptyState` renders; optionally add an error/retry branch.
- **Risk:** safe-mechanical

### H3 · i18n · BackendDetailPage inline "Edit Account" form is hardcoded English
- **Page:** ai-backends
- **File:** `frontend/src/views/BackendDetailPage.vue:100`
- **Evidence:** `<h3>Edit Account</h3>`, `<label>Account Name *</label>`, `Email`, `Login email for this account`, `Config Path`, `API Key Environment Variable`, `Plan` — all bare literals. The rest of the view already uses `t('backendDetail.*')` (`useI18n` at line 272); this block is the lone un-internationalized region.
- **Fix:** Wrap every label/heading/`<small>` in `t()` under new `backendDetail.editForm.*` keys; add key-identical to all four locales.
- **Risk:** safe-mechanical

## MEDIUM

### M1 · bug · AnomalyDetectionCard.acknowledge() reports success when the request fails
- **Page:** dashboard
- **File:** `frontend/src/views/dashboards/cards/AnomalyDetectionCard.vue:109`
- **Evidence:** `catch { anomaly.acknowledged = true; showToast(t('anomalyDetectionCard.toast.acknowledged'),'success'); }` — a failed acknowledge is reported as success and flips local state.
- **Fix:** In catch, do not flip `acknowledged` and do not toast success; show an error toast (new `anomalyDetectionCard.toast.acknowledgeFailed` key, added to all four locales).
- **Risk:** safe-mechanical

### M2 · dead-control · CrossTeamInsights "Export Report" is a no-op that toasts success
- **Page:** dashboard
- **File:** `frontend/src/views/dashboards/cards/CrossTeamInsightsCard.vue:87`
- **Evidence:** `function exportReport(){ showToast(t('crossTeamInsightsCard.toast.exported'),'success'); }` — claims "report exported" while doing nothing.
- **Fix:** Implement a real export (serialize teams/orgFindings/topRiskyRepos to CSV/JSON, download via Blob + anchor), or remove the button until export exists.
- **Risk:** safe-mechanical

### M3 · i18n · Project status enum rendered untranslated
- **Page:** project-detail
- **File:** `frontend/src/components/projects/ProjectStatusCard.vue:34`
- **Evidence:** `{{ project.status }}` renders raw `active`/`archived`/`planning`; component imports no `useI18n`; `projectStatus.*` keys absent from all locales.
- **Fix:** Render `{{ t(\`projectStatus.${project.status}\`) }}`, add `projectStatus.active/archived/planning` key-identical to all four locales; keep `getStatusClass` for CSS only.
- **Risk:** safe-mechanical

### M4 · a11y · Icon-only delete button on agent card has no accessible name
- **Page:** agents
- **File:** `frontend/src/views/AgentsPage.vue:291`
- **Evidence:** delete `<button>` contains only a spinner span + trash `<svg>`, no text/aria — announced as unlabeled "button" unlike sibling Run/Enable text buttons.
- **Fix:** Add `:aria-label="t('common.delete')"` (key present all four locales).
- **Risk:** safe-mechanical

### M5 · a11y · Icon-only delete button has no accessible label (CommandsPage)
- **Page:** commands
- **File:** `frontend/src/views/CommandsPage.vue:490`
- **Evidence:** danger button renders only a trash `<svg>`, no text node.
- **Fix:** Add `:aria-label="t('common.delete')"` (and/or `:title`).
- **Risk:** safe-mechanical

### M6 · a11y · Icon-only delete button has no accessible name (RulesPage)
- **Page:** rules
- **File:** `frontend/src/views/RulesPage.vue:505`
- **Evidence:** trash `<svg>` is the only child of the danger button.
- **Fix:** Add `:aria-label="t('common.delete')"`.
- **Risk:** safe-mechanical

### M7 · a11y · Enabled toggle is a `<div>` with `@click` only — not keyboard-operable (RulesPage)
- **Page:** rules
- **File:** `frontend/src/views/RulesPage.vue:556`
- **Evidence:** `<div class="toggle-switch" @click="editForm.enabled = !editForm.enabled">` inside a `<label>` with no `<input>` — not focusable, no switch role/state.
- **Fix:** Add `role="switch"`, `:aria-checked="editForm.enabled"`, `tabindex="0"`, `@keydown.enter/@keydown.space` (or use a `<button>`/checkbox).
- **Risk:** safe-mechanical

### M8 · i18n · "Ouroboros" button label is a bare literal, not in t()
- **Page:** super-agents
- **File:** `frontend/src/views/SuperAgentsPage.vue:411`
- **Evidence:** literal `Ouroboros` in the action row; every sibling uses `t()` (`t('superAgents.inspector')` L395, `t('common.delete')` L417).
- **Fix:** Route via `t('superAgents.ouroboros')`, add key to all four locales (value may stay "Ouroboros" — make it a managed key).
- **Risk:** safe-mechanical

### M9 · bug/i18n · Scheduled-trigger time always labeled "KST" regardless of actual timezone
- **Page:** triggers
- **File:** `frontend/src/components/triggers/TriggerDetailPanel.vue:340`
- **Evidence:** `…<strong>{{ selectedTrigger.schedule_time || '00:00' }}</strong> KST` — hardcoded `KST`. `AddTriggerModal.vue:217` stores the real browser tz; `schedule_timezone` exists on the Trigger type. Any non-KST operator sees a mislabeled time. Also the only bare `KST` literal not in vue-i18n.
- **Fix:** Render `{{ selectedTrigger.schedule_timezone || '' }}` instead of the literal `KST`.
- **Risk:** safe-mechanical

### M10 · a11y · Export-format selector cards are click-only `<div>`s (keyboard-inaccessible radio group)
- **Page:** plugins
- **File:** `frontend/src/components/plugins/ExportPluginModal.vue:117`
- **Evidence:** two mutually-exclusive format cards (Claude L117–131, Agented L133–149) are plain `<div>`s with only class/`:class`/`@click` — no `tabindex`/`role`/keydown; a keyboard-only user cannot change export format.
- **Fix:** Convert each to `<button type="button">` (or `role="radio"` + `tabindex="0"` + `@keydown.enter/space` + `aria-checked`) wrapped in `role="radiogroup"`.
- **Risk:** safe-mechanical *(implementation is mechanical; the visual active-state should be glanced at — see N-note)*

### M11 · a11y · Toggle-switch buttons have no accessible name (GeneralSettings)
- **Page:** settings
- **File:** `frontend/src/components/settings/GeneralSettings.vue:340`
- **Evidence:** bare `<button class="toggle-switch">` with empty `<span class="toggle-knob">`; same pattern at `yoloMode L368`, `sessionDefaultYolo L395`, `monitoringConfig.enabled L428`, per-account toggle `L470`. Zero aria/role in file. A `<label>` wrapping a `<button>` does not name it.
- **Fix:** Add `role="switch"`, `:aria-checked`, and `:aria-label` (e.g. `t('settings.general.autoRefreshTitle')`, present all four locales) to each toggle-switch button.
- **Risk:** safe-mechanical

### M12 · a11y · Toggle-switch buttons have no accessible name (GrdSettings)
- **Page:** settings
- **File:** `frontend/src/components/settings/GrdSettings.vue:67`
- **Evidence:** bare `<button class="toggle-switch">` for `autoInitEnabled`; same at `syncOnSessionComplete L89`. Zero aria/role.
- **Fix:** Add `role="switch"`, `:aria-checked`, `:aria-label` (`t('settings.grd.autoInitTitle')` / `t('settings.grd.syncOnCompleteTitle')`, present all four locales).
- **Risk:** safe-mechanical

### M13 · a11y · Icon-only modal close (×) has no accessible name (Marketplace ×3)
- **Page:** marketplace
- **Files:**
  - `frontend/src/views/marketplace/MarketplacePlugins.vue:242`
  - `frontend/src/views/marketplace/MarketplaceMcpServers.vue:254`
  - `frontend/src/views/marketplace/MarketplaceSuperAgents.vue:175`
- **Evidence:** `<button class="close-btn" @click="closeDetail">&times;</button>` — `&times;` glyph is the only content; each view's footer Close button already uses `t('common.close')`.
- **Fix:** Add `:aria-label="t('common.close')"` to each (key present all four locales).
- **Risk:** safe-mechanical

### M14 · i18n · BackendDetailPage edit-form placeholders hardcoded English
- **Page:** ai-backends
- **File:** `frontend/src/views/BackendDetailPage.vue:111`
- **Evidence:** `placeholder="e.g., Personal, Work"` (L111), `e.g., user@example.com` (L120), `e.g., ~/.claude-work` (L130), `e.g., ANTHROPIC_API_KEY_WORK` (L140).
- **Fix:** Bind `:placeholder="t('backendDetail.editForm.*Placeholder')"`; add four new placeholder keys to all locales.
- **Risk:** safe-mechanical

### M15 · i18n · BackendDetailPage select-option labels hardcoded English
- **Page:** ai-backends
- **File:** `frontend/src/views/BackendDetailPage.vue:147`
- **Evidence:** `Select plan…` (L147), `Default/Low/Medium/High` (L155–158), `Concise/Detailed` (L166–167), `Controls how much reasoning…` (L160), `Controls output verbosity` (L169). Note: `common.low/medium/high` do NOT exist in en.json.
- **Fix:** Route each option/`<small>` through new `backendDetail.editForm.*` keys; add to all locales (do not assume `common.*` reuse).
- **Risk:** safe-mechanical

### M16 · i18n · BackendDetailPage edit-form buttons + "Set as default" label hardcoded
- **Page:** ai-backends
- **File:** `frontend/src/views/BackendDetailPage.vue:176`
- **Evidence:** `Set as default account` (L176), `Cancel` (L179), `{{ isSaving ? 'Saving...' : 'Update' }}` (L181). `common.update`/`common.saving` do NOT exist.
- **Fix:** Use `t('common.cancel')` for Cancel; add `backendDetail.editForm.saving/update/setDefault` to all locales.
- **Risk:** safe-mechanical

### M17 · i18n · BackendDetailPage toast & fallback messages hardcoded English
- **Page:** ai-backends
- **File:** `frontend/src/views/BackendDetailPage.vue:338`
- **Evidence:** `Installing ${name} CLI...` (L338), `CLI installed` (L341), `Account saved successfully` (L471), `Account updated` (L592), `Failed to delete account` (L616), `Login completed successfully` (L675/681), `Rate limit cleared` (L661), `Failed to load backend` (L433). Sibling AIBackendsPage already internationalizes toasts via `aIBackends.toast*`.
- **Fix:** Route all through new `backendDetail.toast*` keys (named interpolation for the backend name); add key-identical to all locales.
- **Risk:** safe-mechanical

### M18 · i18n · BackendDetailPage capabilityList builds hardcoded English labels
- **Page:** ai-backends
- **File:** `frontend/src/views/BackendDetailPage.vue:367`
- **Evidence:** computed returns `{label:'JSON Output'}`,`'Token Usage'`,`'Streaming'`,`'Non-Interactive'`, rendered at `BackendInfoSection.vue:51`.
- **Fix:** Reuse existing `t('aIBackends.capJsonOutput'/'capTokenUsage'/'capStreaming'/'capNonInteractive')` — keys already exist with these exact strings (verified-ready across all four locales).
- **Risk:** safe-mechanical

### M19 · i18n · Strategy status enum rendered raw, not localized
- **Page:** competitor-intel
- **File:** `frontend/src/views/CompetitorIntelView.vue:563`
- **Evidence:** `<span class="ci-kind">{{ st.status }}</span>` renders raw `proposed|approved|rejected|implementing|done`; `competitorIntel` namespace has zero status keys.
- **Fix:** Add a `statusLabel()` mapping each enum to `t('competitorIntel.status<Proposed|Approved|Rejected|Implementing|Done>')`; add the 5 keys key-identical to all locales.
- **Risk:** safe-mechanical

### M20 · redundancy · Duplicate top-level nav label "Triggers" (Forge + Observability)
- **Page:** sidebar-shell
- **File:** `frontend/src/components/layout/AppSidebar.vue:897`
- **Evidence:** Forge toggle (L664) and Observability toggle (L897) both render `t('nav.triggers')`; user sees two top-level "Triggers" entries. The second submenu's aria-label is `nav.triggerHistory` (L910) but its visible label stays `nav.triggers`.
- **Fix:** Change L897 visible label to `t('nav.triggerHistory')` (key present all four locales).
- **Risk:** safe-mechanical

### M21 · i18n · AppHeader search button label/title hardcoded English
- **Page:** sidebar-shell
- **File:** `frontend/src/components/layout/AppHeader.vue:311`
- **Evidence:** `aria-label="Search" title="Search (Cmd+K)"` literal; `useI18n` already bound (L8). No `header` namespace in any locale.
- **Fix:** `:aria-label="t('header.search')"` / `:title="t('header.searchHint')"`; add keys to all locales.
- **Risk:** safe-mechanical

### M22 · i18n · AppHeader notification bell label/title hardcoded English
- **Page:** sidebar-shell
- **File:** `frontend/src/components/layout/AppHeader.vue:324`
- **Evidence:** `aria-label="Notifications" title="Notifications"` literal.
- **Fix:** `:aria-label="t('header.notifications')"` / `:title=…`; add key to all locales.
- **Risk:** safe-mechanical

### M23 · i18n · AppHeader notification empty-state copy hardcoded English
- **Page:** sidebar-shell
- **File:** `frontend/src/components/layout/AppHeader.vue:336`
- **Evidence:** `<p>No notifications</p>`, `<p class="subtitle">You're all caught up</p>`.
- **Fix:** `{{ t('header.notificationsEmpty') }}` / `{{ t('header.notificationsEmptySubtitle') }}`; add keys to all locales.
- **Risk:** safe-mechanical

### M24 · i18n · AppHeader profile avatar/dropdown labels hardcoded English
- **Page:** sidebar-shell
- **File:** `frontend/src/components/layout/AppHeader.vue:344`
- **Evidence:** `aria-label="Profile menu"` (L344), `<div class="dropdown-label">User</div>` (L348), `Settings` (L350), `Sign Out` (L351).
- **Fix:** `:aria-label="t('header.profileMenu')"`, `{{ t('header.user') }}`, `{{ t('nav.settings') }}`, `{{ t('header.signOut') }}`; add missing keys to all locales.
- **Risk:** safe-mechanical

### M25 · i18n · AppHeader breadcrumb segment-labels map hardcoded English
- **Page:** sidebar-shell
- **File:** `frontend/src/components/layout/AppHeader.vue:134`
- **Evidence:** `segmentLabels = { 'products':'Products', 'projects':'Projects', … 'sketch-chat':'Sketch', 'audit-history':'Audit History' }`; `resolveSegmentLabel` returns these literals — breadcrumb always English though same nouns exist as translated `nav.*` keys.
- **Fix:** Map each segment to an i18n key (`'products':'nav.products'`) and resolve via `t()`, title-case fallback only for unknown segments.
- **Risk:** safe-mechanical

## LOW

### L1 · a11y · SHARED — Icon-only modal close (× / SVG) has no accessible label
- **Category:** a11y · **Risk:** safe-mechanical
- **Shared component pattern** (`modal-close` / `close-btn` / `btn-close` icon-only buttons). Codebase-wide: ~66 `modal-close` usages, 0 with `aria-label`. **Affected files/lines** (each is `<button …>&times;</button>` or SVG-only, no text node):
  - `frontend/src/views/ProductsPage.vue:286`
  - `frontend/src/components/projects/ProjectDiscoveryModal.vue:123`
  - `frontend/src/views/ProjectsPage.vue:316`
  - `frontend/src/views/ProjectDashboard.vue:897` (SVG X)
  - `frontend/src/components/triggers/AddTriggerModal.vue:247` (SVG X)
  - `frontend/src/views/PluginsPage.vue:373` (also `:428`, `ExportPluginModal.vue:94`, `ImportPluginModal.vue:115`)
  - `frontend/src/views/MySkills.vue:258` (SVG X)
  - `frontend/src/views/SettingsPage.vue:216`
- **Fix (one shared change):** Add `:aria-label="t('common.close')"` to every icon-only dismiss button. `common.close` is present key-identical in all four locales (en "Close" / ko "닫기" / ja "閉じる" / zh "关闭"). Prefer a single sweep over per-page patches. (Marketplace × close buttons are tracked at M13 only because they're MEDIUM-confidence dialog-dismiss controls; same fix.)

### L2 · a11y · TriggerDetailPanel path-remove button is icon-only, no label
- **Page:** triggers · **File:** `frontend/src/components/triggers/TriggerDetailPanel.vue:516`
- **Evidence:** `<button class="btn-icon btn-delete" @click="removePath(path)"><svg…/></button>` — sibling budget-delete (L481) already sets a `:title`.
- **Fix:** Add `:title`/`aria-label="t('common.remove')"` (key present all four locales). · Risk: safe-mechanical

### L3 · a11y · McpServersPage create-server form labels not associated with inputs
- **Page:** mcp-servers · **File:** `frontend/src/views/McpServersPage.vue:312`
- **Evidence:** 6 bare `<label>` siblings, zero `for=` (only `for=` hit at L239 is a `v-for`); controls have no `id` (name L312, server_type L316, command L324, args L328, url L332, description L336).
- **Fix:** Add unique `id` + matching `for=` to all 6 pairs. · Risk: safe-mechanical

### L4 · a11y · Marketplace MCP install-form inputs have no associated `<label>`
- **Page:** marketplace · **File:** `frontend/src/views/marketplace/MarketplaceMcpServers.vue:277`
- **Evidence:** bare `<label>` siblings, controls without `id` (serverType, command, arguments, url, envVars, timeout — L278–304).
- **Fix:** Add `id` + `for=` to all 6 pairs (or wrap controls in their labels). · Risk: safe-mechanical

### L5 · a11y · SuperAgentsPage create-modal form labels have no for/id
- **Page:** super-agents · **File:** `frontend/src/views/SuperAgentsPage.vue:433`
- **Evidence:** bare `<label>` siblings for name (L433), description (L437), backend-type (L441). Pattern widespread (e.g. AgentDesignPage.vue).
- **Fix:** Add matching `id`/`for=` per field; prefer a house-wide sweep. · Risk: safe-mechanical

### L6 · a11y · MySkills toggle buttons have no accessible name/state
- **Page:** skills · **File:** `frontend/src/views/MySkills.vue:226`
- **Evidence:** `<label class="toggle-row"><span>…</span><button class="toggle-btn" @click.stop="toggleEnabled(skill)"><span class="toggle-knob"/></button></label>` — a `<label>` doesn't name a `<button>`; also harness toggle L235.
- **Fix:** Add `role="switch"`, `:aria-checked`, `:aria-label`/`aria-labelledby` → adjacent text span. · Risk: safe-mechanical

### L7 · a11y · SkillDetailPage toggle buttons have no accessible name/state
- **Page:** skills · **File:** `frontend/src/views/SkillDetailPage.vue:179`
- **Evidence:** `<button class="toggle-btn" @click="editEnabled = !editEnabled"><span class="toggle-knob"/></button>`; harness toggle L188.
- **Fix:** Add `role="switch"`, `:aria-checked="editEnabled"`, aria-label/labelledby. · Risk: safe-mechanical

### L8 · a11y · HooksPage icon-only delete button has no accessible label
- **Page:** hooks · **File:** `frontend/src/views/HooksPage.vue:487`
- **Evidence:** danger button renders only a trash `<svg>`, no text/aria.
- **Fix:** Add `:aria-label="t('common.delete')"`. · Risk: safe-mechanical

### L9 · a11y · SlackNotificationsPage icon-only "+" add-channel button has no label
- **Page:** integrations · **File:** `frontend/src/views/SlackNotificationsPage.vue:204`
- **Evidence:** `<button class="btn-add" @click="addChannel">+</button>` — only glyph "+".
- **Fix:** `:aria-label="t('slackNotifications.addChannel')"` (key present all locales). · Risk: safe-mechanical

### L10 · a11y · TeamsNotificationChannels "✕" delete-channel button has no label
- **Page:** integrations · **File:** `frontend/src/views/TeamsNotificationChannelsPage.vue:310`
- **Evidence:** `<button class="btn-delete" @click="deleteChannel(ch.id)">✕</button>` — only "✕".
- **Fix:** Add `:aria-label` (e.g. `t('teamsNotificationChannels.toast.channelRemoved')` or a dedicated remove-channel key). · Risk: safe-mechanical

### L11 · a11y · TeamsNotificationChannels "✕" modal-close button has no label
- **Page:** integrations · **File:** `frontend/src/views/TeamsNotificationChannelsPage.vue:354`
- **Evidence:** `<button class="btn-close" @click="showAddModal=false">✕</button>`.
- **Fix:** Add `:aria-label="t('common.cancel')"` or a dedicated close key. · Risk: safe-mechanical

### L12 · a11y · TeamsNotificationChannels enable/disable toggle (hidden checkbox) has no label
- **Page:** integrations · **File:** `frontend/src/views/TeamsNotificationChannelsPage.vue:306`
- **Evidence:** `<label class="toggle"><input type="checkbox" :checked="ch.enabled" @change="toggleChannel(ch)"/><span class="toggle-track"/></label>` — label wraps only a styling span.
- **Fix:** Add `:aria-label` on the input (e.g. enabled/disabled toast keys, both present all locales). · Risk: safe-mechanical

### L13 · a11y · MemorySystemSettings disclosure button glyph-only, no aria-label/aria-expanded
- **Page:** settings · **File:** `frontend/src/components/settings/MemorySystemSettings.vue:354`
- **Evidence:** `<button class="disclosure" @click="toggleDetails(p)">▸</button>` — ▸ glyph only; no aria-expanded/label.
- **Fix:** Add an `aria-label` (key-identical key) + `:aria-expanded="expandedProjectId === p.project_id"`. · Risk: safe-mechanical

### L14 · a11y · AppSidebar API Docs external link is target=_blank without rel="noopener"
- **Page:** sidebar-shell · **File:** `frontend/src/components/layout/AppSidebar.vue:991`
- **Evidence:** `<a href="/docs" target="_blank" class="external-link">` — exposes `window.opener` (tabnabbing).
- **Fix:** Add `rel="noopener noreferrer"`. · Risk: safe-mechanical

### L15 · i18n · SuperAgentPlayground session badges "leader"/"worktree" hardcoded
- **Page:** super-agents · **File:** `frontend/src/views/SuperAgentPlayground.vue:291`
- **Evidence:** `>leader</span>` / `>worktree</span>` literal text. A translated "Leader" already exists (`superAgentInspector.badge.leader` en.json:7445).
- **Fix:** `t('superAgentPlayground.badge.leader'/'badge.worktree')`; add keys key-identical to all locales. · Risk: safe-mechanical

### L16 · i18n · WorkflowsPage card trigger badge renders raw trigger_type
- **Page:** workflows · **File:** `frontend/src/views/WorkflowsPage.vue:247`
- **Evidence:** `{{ wf.trigger_type }}` renders raw `file_watch` etc., while the same view's create modal localizes identical values via `workflows.triggerType.*` (L307–311).
- **Fix:** Render via existing `workflows.triggerType.*` with a snake→camel map (`file_watch→fileWatch`). · Risk: safe-mechanical

### L17 · mock-data/i18n · WorkflowPlayground stub generator renders hardcoded English prose
- **Page:** workflows · **File:** `frontend/src/views/WorkflowPlaygroundPage.vue:238`
- **Evidence:** `generateDeploy/Review/Data/MonitorWorkflowResponse` (L248–380) each return hardcoded English templates pushed as assistant messages; fires when `isDemoMode` (default true) or backend `.catch()`.
- **Fix:** Move prose into `workflowPlayground.stub.*` keys (key-identical, all locales), keep fenced JSON graph blocks as-is. · Risk: safe-mechanical

### L18 · i18n · WorkflowPlayground auto-created workflow name/description hardcoded English
- **Page:** workflows · **File:** `frontend/src/views/WorkflowPlaygroundPage.vue:396`
- **Evidence:** `name: 'AI-Generated Workflow ${time}'`, `description: 'Generated by AI Workflow Playground'` — persisted, later shown in the workflow list.
- **Fix:** `t('workflowPlayground.generated.name', { time })` / `t('workflowPlayground.generated.description')`; add subtree to all locales. · Risk: safe-mechanical

### L19 · bug/i18n · CommandsPage create-modal placeholder has literal `\n` and is hardcoded English
- **Page:** commands · **File:** `frontend/src/views/CommandsPage.vue:577`
- **Evidence:** `placeholder="# Command Content\n\nDescribe what this command should do..."` — in a static attribute the `\n` are literal backslash-n; also untranslated.
- **Fix:** `:placeholder="t('commands.field.contentPlaceholder')"` (key already used by SlideOver L526) — fixes both bugs. · Risk: safe-mechanical

### L20 · bug · SkillCreatePreviewDrawer fallback renders literal "&lt;name&gt;" instead of "<name>"
- **Page:** skills · **File:** `frontend/src/components/skills/SkillCreatePreviewDrawer.vue:183`
- **Evidence:** `?? '.claude/skills/&lt;name&gt;'` — Vue text interpolation escapes its output, so the entities show verbatim.
- **Fix:** Use plain `'.claude/skills/<name>'` (Vue escapes for display); optionally move behind `skillCreatePreviewDrawer.pathPlaceholder`. · Risk: safe-mechanical

### L21 · i18n · CompetitorIntel lookalike kind chip renders raw 'company'
- **Page:** competitor-intel · **File:** `frontend/src/views/CompetitorIntelView.vue:672`
- **Evidence:** `kindLabel` (L108) switches only github_repo/arxiv/product_url/hn_query; `company`/`product` uncased → returns the bare string. `MarketLookalike.kind` doc says 'company' is a scan's dominant kind.
- **Fix:** Add `case 'company': return t('competitorIntel.kindCompany')` + `case 'product': return t('competitorIntel.kindProduct')`; add `kindCompany` key-identical (kindProduct already exists). · Risk: safe-mechanical

### L22 · dead-control · MarketplaceSettings dead loading branch (isLoading never set true)
- **Page:** settings · **File:** `frontend/src/components/settings/MarketplaceSettings.vue:233`
- **Evidence:** `const isLoading = ref(false)` (L26) is never reassigned; `v-if="isLoading"` spinner (L233) is permanently unreachable.
- **Fix:** Remove the dead spinner block + unused ref, or wire it to the parent's real loading flag (SettingsPage passes `marketplaces` but not its loading state). · Risk: safe-mechanical

---

# NEEDS-VISUAL-CHECK (browser-verify first)

These touch interactive behavior, layout/styling, API alignment, or routing where the correct fix depends on observed runtime behavior. Verify in a browser before/while fixing.

## HIGH

### NV-H1 · missing-state · Auth pages (login/signup/forgot/reset) render the full app sidebar
- **Page:** sidebar-shell
- **File:** `frontend/src/composables/useAppLayout.ts:18`
- **Evidence:** `isWelcomePage = route.name === 'welcome'`; `App.vue:213` renders bare fullscreen only `v-if="isWelcomePage"`, else mounts `AppShell` (header+sidebar). `router/routes/auth.ts:14–37` defines `login`/`signup`/`forgot-password`/`reset-password` as `public/fullBleed`; `guards.ts:150` redirects unauthenticated users to `login`. None equal `welcome`, so `/login` renders full app nav around the login form.
- **Fix:** Broaden the fullscreen condition via a shared route-meta flag (all four already set `fullBleed: true`) or an explicit name set: `FULLSCREEN_ROUTES = ['welcome','login','signup','forgot-password','reset-password']`.
- **Verify:** load each auth route, confirm sidebar/header are gone and the form is centered fullscreen. · Risk: needs-visual-check

### NV-H2 · dead-control · "Sign Out" button is a no-op
- **Page:** sidebar-shell
- **File:** `frontend/src/components/layout/AppHeader.vue:53`
- **Evidence:** `handleSignOut(){ /* No-op */ showProfileDropdown.value = false; }` wired to the visible "Sign Out" button (L351). Clicking only closes the dropdown — never clears session/API key or navigates.
- **Fix:** Clear stored API key (`services/api` `setApiKey`) → `router.push({ name: 'login' })`, calling a backend logout first if one exists. Until implemented, do not render the control.
- **Verify:** confirm redirect to login and that protected routes re-challenge after sign-out. · Risk: needs-visual-check

### NV-H3 · dead-control · CompetitorIntel "Implement" button is dead — no handler, no API
- **Page:** competitor-intel
- **File:** `frontend/src/views/CompetitorIntelView.vue:606`
- **Evidence:** `<button type="button" class="ci-implement" :disabled="!st.legal_cleared_at" …>` has no `@click`, isn't inside the add-source `<form>`. `competitor-intel.ts` exposes no implement/materialize method; `Strategy.plan_id` documented "null in this MVP". Once all 7 legal items affirmed, the button enables and clicking does nothing.
- **Fix:** Until the materialize path ships, keep it permanently disabled with a "materialize not yet available" title (new i18n key); or wire `@click` to a real endpoint once one exists.
- **Verify:** confirm the disabled/enabled transition and the title copy render correctly. · Risk: needs-visual-check

## MEDIUM

### NV-M1 · dead-control · ProjectDiscoveryModal "Direct only" checkbox cannot be toggled off
- **Page:** projects · **File:** `frontend/src/components/projects/ProjectDiscoveryModal.vue:149`
- **Evidence:** `<input type="checkbox" :checked="!nested" @change="nested = false"/>` — `@change` unconditionally forces `nested=false`; sibling "Scan nested" (L153) is `v-model="nested"`. Clicking when already checked is a no-op and re-renders checked, so it can never be unchecked alone.
- **Fix:** Make it two-way (`@change="nested = !($event.target as HTMLInputElement).checked"`), or collapse the two coupled checkboxes into one checkbox/radio pair driving the single `nested` boolean.
- **Verify:** confirm both checkboxes stay mutually consistent across clicks. · Risk: needs-visual-check

### NV-M2 · bug · SuperAgentInspector "1h" window uses a 24h rollup, mismatching its 1h list
- **Page:** super-agents · **File:** `frontend/src/views/SuperAgentInspectorPage.vue:46`
- **Evidence:** `TIME_WINDOW_TO_DAYS = { '1h':1, '24h':1 }`. Event list fetched `since = now-1h` (L87); rollup fetched `days = 1` → 24h via `rollup(id, days)` (L90). Rollup metrics describe 24h while the timeline below describes 1h. Rollup API accepts only integer `window_days`.
- **Fix:** Add sub-day support to the rollup endpoint or align both on a shared `since` boundary. **Verify the API change before fixing.** · Risk: needs-visual-check

### NV-M3 · bug · HooksPage search/sort apply only to the current server page
- **Page:** hooks · **File:** `frontend/src/views/HooksPage.vue:223`
- **Evidence:** `loadHooks` calls `hookApi.list(undefined, { limit, offset })` — no search/sort; API accepts only projectId/limit/offset. Grid renders `filteredAndSorted` over `hooks.value` (the current 25-item page) client-side; the watch (L235) only resets the page. With >25 hooks, matches on other pages are invisible to search/sort.
- **Fix:** Lower-risk route — fetch all hooks once and paginate client-side (drop server limit/offset, let `usePagination`/`useListFilter` operate over the full set). · Verify: confirm search finds items beyond page 1 and pagination still behaves. · Risk: needs-visual-check

### NV-M4 · dead-control · SlackNotifications "Delivery Logs" tab is permanently empty
- **Page:** integrations · **File:** `frontend/src/views/SlackNotificationsPage.vue:228`
- **Evidence:** `logs = ref<NotificationLog[]>([])` is never assigned anywhere; `integrationApi` has no logs endpoint. The Logs tab can never show data (`{{ t('slackNotifications.noLogs') }}` always).
- **Fix:** Either wire a real `integrationApi.logs(id)` fetch on tab-open, or remove the Delivery Logs tab + dead `NotificationLog`/`logs`/`statusColor`/`formatDate` until the backend exists.
- **Verify:** confirm tab removal doesn't break the tab strip layout, or that logs render once wired. · Risk: needs-visual-check

## LOW

### NV-L1 · dead-control · SchedulingCard On-Call severity toggles wired to a constant, no handler
- **Page:** dashboard · **File:** `frontend/src/views/dashboards/cards/SchedulingCard.vue:350`
- **Evidence:** `<input type="checkbox" :checked="sev !== 'low'"/>` bound to static `severityRows` (L179) — no `@change`/`v-model`/persistence; inline comment (L338) confirms a static reference policy.
- **Fix:** Add `disabled` + `aria-disabled` + a "reference only" note, or render the threshold rows as plain static reference (remove the switch affordance). · Verify: confirm the cards still read as informational. · Risk: needs-visual-check

### NV-L2 · a11y · ProjectStatusCard clickable product pill is a non-button span, no keyboard activation
- **Page:** project-detail · **File:** `frontend/src/components/projects/ProjectStatusCard.vue:36`
- **Evidence:** `<span class="meta-pill product" :class="{'entity-link':project.product_id}" @click="… emit('navigateToProductDashboard', …)">` — `.entity-link` is `cursor:pointer` (real click affordance) but the `<span>` has no `role="button"`, `tabindex`, or keydown; keyboard users can't navigate.
- **Fix:** When clickable, add `role="button"`, `tabindex="0"`, `@keydown.enter/@keydown.space`; or render a real `<button>`/`<router-link>` when `product_id` is present. · Verify: confirm focus ring + keyboard activation. · Risk: needs-visual-check

### NV-L3 · bug · TeamsPage topology badge unstyled for hierarchical/human_in_loop/composite
- **Page:** teams · **File:** `frontend/src/views/TeamsPage.vue:422`
- **Evidence:** badge class `'topo-' + team.topology`; per-type CSS exists only for sequential/parallel/coordinator/generator_critic/none. `TopologyType` (and `TopologyPicker.vue:60–75`) include `hierarchical|human_in_loop|composite` → emit `.topo-hierarchical` etc. with no rule → transparent background, inherited color (visually broken).
- **Fix:** Add `.topo-hierarchical`, `.topo-human_in_loop`, `.topo-composite` rules (bg/color pairs), or fall back to neutral `.topo-none` for unknown types. · Verify: render a team of each topology and compare chips. · Risk: needs-visual-check

### NV-L4 · dead-control · TriggerList backend availability badge hardcoded to "unavailable"
- **Page:** triggers · **File:** `frontend/src/components/triggers/TriggerList.vue:40`
- **Evidence:** `isBackendInstalled(_backendType){ return false; }` — every badge renders `unavailable` (L109) regardless of real CLI install state.
- **Fix:** Pass real installed flags from the parent (`TriggerManagement` has claude/opencode status) and key the class off those, or drop the available/unavailable styling (currently conveys no real signal). · Verify: confirm badges reflect actual install state. · Risk: needs-visual-check

### NV-L5 · redundancy · CompetitorIntel lookalike candidate URL renders twice when candidate_repo empty
- **Page:** competitor-intel · **File:** `frontend/src/views/CompetitorIntelView.vue:673`
- **Evidence:** `<span>{{ la.candidate_repo || la.candidate_url }}</span>` then `<a :href="la.candidate_url">{{ la.candidate_url }}</a>` — when `candidate_repo` is empty the same URL renders twice (plain text + link).
- **Fix:** Gate the first span: `v-if="la.candidate_repo && la.candidate_repo !== la.candidate_url"`. · Verify: check both empty and populated `candidate_repo` rows. · Risk: needs-visual-check (low confidence 0.5)

### NV-L6 · redundancy · Duplicate nav label "Playground" (Workflows + Skills submenus)
- **Page:** sidebar-shell · **File:** `frontend/src/components/layout/AppSidebar.vue:785`
- **Evidence:** Workflows submenu (L658) and Skills submenu (L785) both render `t('nav.playground')`; disambiguated only by their collapsible parent.
- **Fix:** Add distinct `nav.workflowPlayground` / `nav.skillsPlayground` to all four catalogs, or prefix with the parent. · Verify: confirm both submenus read distinctly when expanded. · Risk: needs-visual-check (treated as needs-visual since it depends on sidebar context/expansion state)

### NV-L7 · i18n · AppHeader breadcrumb root "Home" label hardcoded
- **Page:** sidebar-shell · **File:** `frontend/src/components/layout/AppHeader.vue:187`
- **Evidence:** `[{ label: 'Home', to: { name: 'dashboards' } }]` (L185/L187) flows into `{{ seg.label }}` (L278/284/297).
- **Fix:** Use `t('header.home')` (or reuse an existing Home-equivalent nav key) for the root segment. · Verify: confirm breadcrumb renders translated in non-en locales. · Risk: needs-visual-check (paired with the M25 breadcrumb-map change)

---

## Notes for the fixer

- **i18n parity is mandatory:** every new key must be added to `frontend/src/locales/{en,ko,ja,zh}.json` key-identical. Several findings reuse already-present keys (`common.close`, `common.delete`, `common.remove`, `common.cancel`, `aIBackends.cap*`, `workflows.triggerType.*`) — those are safe drop-ins. Findings flagged "key does NOT exist" (e.g. `common.update/saving/low/medium/high`, the `header.*` namespace, `projectStatus.*`, `competitorIntel.status*`) require **new** keys in all four locales.
- **Biggest single win:** L1 (shared icon-only close-button sweep) clears ~10 a11y findings in one change.
- **Highest user-trust risk:** H1/H2 (fabricated dashboard data presented as real) and NV-H2/NV-H3 (dead Sign Out / Implement controls).
- **Do not commit/push** — per task instructions this report is the deliverable.
