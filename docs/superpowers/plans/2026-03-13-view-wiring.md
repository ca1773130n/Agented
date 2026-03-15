# View Wiring Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire all 27 mock/shell Vue views to real backend APIs

**Architecture:** Three tiers — Tier 1 (frontend-only, reuse existing APIs), Tier 2 (new aggregation endpoints), Tier 3 (new DB tables + full CRUD). Each tier can be executed in parallel within itself.

**Tech Stack:** Flask + flask-openapi3, SQLite (raw), Pydantic v2, Vue 3 + TypeScript

---

## Shared Patterns

All tasks follow the same structural patterns. Reference these when implementing any task.

### Backend: Adding a New Route

```python
# backend/app/routes/new_feature.py
from flask_openapi3 import APIBlueprint, Tag
tag = Tag(name="NewFeature", description="...")
new_feature_bp = APIBlueprint("new_feature", __name__, url_prefix="/admin", abp_tags=[tag])

@new_feature_bp.get("/new-feature")
def list_items():
    items = get_all_items()  # from app.db module
    return {"items": items}
```

Register in `backend/app/routes/__init__.py`:
```python
from .new_feature import new_feature_bp
# Add to admin_blueprints list for rate limiting
# Add app.register_api(new_feature_bp) in register_blueprints()
```

### Backend: Adding a New DB Table

1. Add `CREATE TABLE IF NOT EXISTS ...` to `backend/app/db/schema.py` inside `create_fresh_schema()`
2. Add a migration step in `backend/app/db/migrations.py` (append to `VERSIONED_MIGRATIONS` list)
3. Create `backend/app/db/new_module.py` with CRUD functions using `get_connection()` context manager
4. Export functions from `backend/app/db/__init__.py`

### Backend: Entity ID Convention

Use prefixed IDs with 6-char random suffix. Add generator to `backend/app/db/ids.py`:
```python
SOME_PREFIX = "find-"  # or "mem-", "etag-", "pipe-", etc.
```

### Frontend: Adding a New API Module

```typescript
// frontend/src/services/api/new-feature.ts
import { apiFetch } from './client';

export interface NewItem { id: string; name: string; /* ... */ }

export const newFeatureApi = {
  list: () => apiFetch<{ items: NewItem[] }>('/admin/new-feature'),
  create: (data: Omit<NewItem, 'id'>) =>
    apiFetch<NewItem>('/admin/new-feature', { method: 'POST', body: JSON.stringify(data) }),
  // ...
};
```

Export from `frontend/src/services/api/index.ts`:
```typescript
export { newFeatureApi } from './new-feature';
```

### Frontend: Wiring a Vue View from Mock to Real

1. Add `onMounted` to vue imports
2. Import the API module
3. Replace hardcoded `ref([...mock...])` with `ref<Type[]>([])`
4. Add `loading = ref(false)` and `error = ref<string | null>(null)`
5. Add `onMounted(async () => { loading.value = true; try { ... } catch { ... } finally { loading.value = false; } })`
6. Wire mutation functions (create/update/delete) to API calls with optimistic updates
7. Add `v-if="!loading"` guard and error display in template

### Shared File Conflict Resolution (Tier 3)

These files are modified by ALL Tier 3 tasks — coordinate changes carefully:
- `backend/app/db/schema.py` — each task appends a `CREATE TABLE IF NOT EXISTS` block
- `backend/app/db/migrations.py` — each task appends a migration entry to `VERSIONED_MIGRATIONS`
- `backend/app/routes/__init__.py` — each task adds an import + `app.register_api()` call
- `frontend/src/services/api/index.ts` — each task adds an export line

**Strategy:** When running tasks in parallel, apply changes to these shared files sequentially after all other files are created. Each change is an append-only line addition, so merge conflicts are minimal.

### Verification (Required After Every Task)

```bash
cd backend && uv run pytest                # Backend tests pass
cd frontend && npm run test:run            # Frontend tests pass
just build                                  # Build passes (vue-tsc type checking)
```

---

## Tier 1: Frontend-Only Wiring

These views reuse existing API endpoints. No backend changes needed.

---

### Task 1: ExecutionTimelinePage

**Files:**
- Modify: `frontend/src/services/api/triggers.ts` — add `date_from`/`date_to` params to `executionApi.listAll`
- Modify: `frontend/src/views/ExecutionTimelinePage.vue`

**What to do:**
- [ ] Extend `executionApi.listAll` options to accept `date_from?: string` and `date_to?: string` query params
- [ ] Replace static `executions` mock array with `executions = ref<ExecutionBar[]>([])`
- [ ] Add `fetchExecutions()` async function in `onMounted`:
  - Call `executionApi.listAll({ limit: 500, date_from })` with `date_from = new Date(Date.now() - windowMs).toISOString()`
  - Map each `Execution` to `ExecutionBar`: status `'completed'` -> `'success'`, `startTs` = `Date.parse(started_at) - windowStart`, `durationMs` = `duration_ms ?? 0`, `trigger` = `trigger_type`
- [ ] Add `watch(windowMinutes, fetchExecutions)` to re-fetch on time window change
- [ ] Make `now` reactive (`ref(Date.now())`) and update in `fetchExecutions`

---

### Task 2: LiveExecutionTerminal

**Files:**
- Modify: `frontend/src/router/routes/misc.ts` — change path to `/executions/:executionId/terminal`, add `props: true`
- Modify: `frontend/src/views/LiveExecutionTerminal.vue`

**What to do:**
- [ ] Add `const props = defineProps<{ executionId: string }>()` (from route param)
- [ ] Remove hardcoded `executionId`, `botName`, `allLines`, `sections` refs and the `setInterval` mock loop
- [ ] In `onMounted`: call `executionApi.get(props.executionId)` for metadata (bot name, status, existing logs)
- [ ] Parse `execution.stdout_log` + `stderr_log` into `allLines` for completed executions
- [ ] If `status === 'running'`, use `useEventSource` composable with `executionApi.streamLogs(props.executionId)`:
  - `log` event: push `{ text: data.content, type: data.stream }` to `allLines`
  - `status` event: update `status.value`
  - `complete` event: update status, close SSE
- [ ] Reference implementation: `frontend/src/components/triggers/ExecutionLogViewer.vue`

---

### Task 3: ExecutionTimeTravelDebugger

**Files:**
- Modify: `frontend/src/views/ExecutionTimeTravelDebugger.vue`

**What to do:**
- [ ] Replace hardcoded `executions` array with `ref<Execution[]>([])`, loaded via `executionApi.listAll({ limit: 20 })` in `onMounted`
- [ ] Replace hardcoded `frames` array with `ref<ExecutionFrame[]>([])`
- [ ] Add `buildFrames(exec: Execution): ExecutionFrame[]` pure function that derives 7 frames from a single execution record:
  - Frame 0: Trigger Received (from `trigger_type` + `started_at`)
  - Frame 1: Context Injected (from `stdout_log` first N lines)
  - Frame 2: Final Prompt Built (from `execution.prompt`, estimate tokens as `chars / 4`)
  - Frame 3: API Call Sent (from `backend_type` + `command`)
  - Frame 4: Model Response Received (from `stdout_log` truncated)
  - Frame 5: Output Formatted (from `stdout_log` line count)
  - Frame 6: Execution Complete (from `status` + `duration_ms` + `finished_at`)
- [ ] Add `watch(selectedExecId, loadFrames)` that calls `executionApi.get(id)` then `buildFrames()`
- [ ] Update template bindings: `e.id` -> `e.execution_id`, `e.botName` -> `e.trigger_name`, `e.runAt` -> `e.started_at`
- [ ] Guard `currentFrameData` computed against empty frames; guard `progress` against division by zero

---

### Task 4: TeamActivityFeedPage

**Files:**
- Create: `frontend/src/services/api/audit.ts` — `auditApi` with `getPersistentEvents()` and `getRecentEvents()`
- Modify: `frontend/src/services/api/index.ts` — export `auditApi`
- Modify: `frontend/src/views/TeamActivityFeedPage.vue`

**What to do:**
- [ ] Create `auditApi` calling `GET /api/audit/events/persistent` (existing endpoint) with params: `entity_type`, `actor`, `start_date`, `end_date`, `limit`, `offset`
- [ ] Add `mapAuditEvent(ev: AuditEvent): ActivityEvent` function that maps:
  - `action` + `outcome` -> `type` (e.g. `execution.complete` + `success` -> `execution`, `trigger.update` -> `config_change`)
  - `action` + `entity_id` -> `summary`
  - `ts` -> `timestamp` (direct), `actor` -> `actor` (direct)
  - Unknown actions default to `config_change`
- [ ] Replace hardcoded `allEvents` array with empty ref, populate via `onMounted` -> `auditApi.getPersistentEvents({ limit: 200 })`
- [ ] Existing filter computeds (`filterType`, `filterActor`, `searchText`, `filteredEvents`) stay unchanged

---

### Task 5: ContextWindowVisualizer

**Files:**
- Modify: `frontend/src/views/ContextWindowVisualizer.vue`

**What to do:**
- [ ] In `onMounted`, call `triggerApi.list()` to populate a trigger selector dropdown
- [ ] On trigger selection, call `triggerApi.get(triggerId)` to load `prompt_template` and `model`, set `promptTemplate.value` and `selectedModel.value`
- [ ] Call `backendApi.list()` on mount to get available models per backend; map into `ModelConfig[]` with hardcoded context window lookup:
  ```typescript
  const CONTEXT_WINDOW_BY_BACKEND: Record<string, number> = {
    claude: 200000, codex: 128000, opencode: 200000, gemini: 1000000,
  };
  ```
- [ ] Replace static `MODELS` const with a reactive `models` ref; fall back to current hardcoded array if API returns nothing
- [ ] Add trigger `<select>` UI element in the template

---

### Task 6: BotDependencyGraph

**Files:**
- Modify: `frontend/src/views/BotDependencyGraph.vue`

**What to do:**
- [ ] Replace static `nodes` and `edges` refs with empty reactive refs
- [ ] In `onMounted`, call `Promise.all([triggerApi.list(), agentApi.list(), teamApi.list()])`
- [ ] Build graph client-side:
  - One synthetic trigger-type node per unique `trigger_source` (color: `#f59e0b`)
  - Each trigger -> `bot` node (color: `#3b82f6`)
  - Each team -> `team` node (color: `#06b6d4`)
  - Each agent -> `agent` node (color: `#34d399`)
  - `fires` edges: trigger-source-node -> trigger-node
  - `owns` edges: team-node -> trigger-node where `team_id` matches
- [ ] Assign x/y positions using layered layout: `x = (index + 1) * (800 / (count + 1))`; trigger-source at y=60, triggers at y=200, teams at y=340, agents at y=460
- [ ] Run simple DFS cycle detection on edges; set `hasCircularDeps` accordingly

---

## Tier 2: New Endpoints (No New Tables)

These views need new backend aggregation endpoints but no schema changes.

---

### Task 7: ExecutionCostEstimator

**Files:**
- Create: `backend/app/routes/model_pricing.py` — `GET /api/models/pricing`
- Modify: `backend/app/routes/__init__.py` — register `model_pricing_bp`
- Create: `frontend/src/services/api/model-pricing.ts`
- Modify: `frontend/src/views/ExecutionCostEstimator.vue`

**Backend endpoint:**
- `GET /api/models/pricing` — returns `{ models: [{ id, name, inputPricePer1M, outputPricePer1M, contextWindow, speed }] }`
- Import `_PRICING` from `backend/app/services/session_cost_service.py`; merge with static `_MODEL_META` dict for name/contextWindow/speed
- No DB queries needed

**Frontend wiring:**
- [ ] Create `modelPricingApi.getModels()` calling the new endpoint
- [ ] Convert `MODELS` from static const to `ref<ModelInfo[]>([...fallback...])` — keep current 3 models as fallback
- [ ] In `onMounted`, fetch and replace; on error, silently keep fallback
- [ ] Update `selectedModelInfo` computed: `MODELS.find(...)` -> `models.value.find(...)`
- [ ] All calculation logic (`promptTokens`, `estimatedCostLow`, etc.) stays unchanged

---

### Task 8: ProjectActivityTimeline

**Files:**
- Create: `backend/app/routes/activity_feed.py` — `GET /api/activity-feed`
- Modify: `backend/app/routes/__init__.py` — register `activity_feed_bp`
- Create: `frontend/src/services/api/activity-feed.ts`
- Modify: `frontend/src/views/ProjectActivityTimeline.vue`

**Backend endpoint:**
- `GET /api/activity-feed` — params: `limit`, `offset`, `entity_type`, `actor`, `start_date`, `end_date`
- Calls `query_audit_events()` from `app.db.audit_events`, maps each raw event into `Activity` shape:
  - `type`: `execution.*` -> `bot_run`, `trigger.*` -> `trigger_fired`, `*.update/create/delete` -> `config_changed`, `team.*` -> `team_action`, failed outcomes -> `execution_failed`
  - `title`: capitalize `action` with spaces
  - `description`: `f"{entity_type} {entity_id} — {outcome}"`
  - `projectId`: `details.get("project_id", entity_id)` (best-effort)
- Returns `{ activities: [...], total: int }`

**Frontend wiring:**
- [ ] Create `activityFeedApi.list(params)` with proper URLSearchParams construction
- [ ] Replace hardcoded `activities` ref with empty ref, load via `onMounted`
- [ ] All filter/group computeds (`projects`, `filtered`, `groupedActivities`) stay unchanged

---

### Task 9: ExecutionFileDiffViewer

**Files:**
- Modify: `backend/app/routes/executions.py` — add `GET /admin/executions/<execution_id>/diff`
- Modify: `frontend/src/services/api/triggers.ts` — add `executionApi.getDiff()`
- Modify: `frontend/src/views/ExecutionFileDiffViewer.vue`

**Backend endpoint:**
- `GET /admin/executions/<execution_id>/diff` — parses `stdout_log` for unified diff blocks using `DiffContextService` / `unidiff.PatchSet`
- Returns `{ diffs: [{ path, status, additions, deletions, chunks: [{ header, lines: [{ type, content, oldLineNo, newLineNo }] }] }] }`
- Status: `is_added_file` -> `"added"`, `is_removed_file` -> `"deleted"`, else `"modified"`

**Frontend wiring:**
- [ ] Add `getDiff: (executionId) => apiFetch<{ diffs: FileDiff[] }>(\`/admin/executions/${executionId}/diff\`)` to `executionApi`
- [ ] In `onMounted`, call `executionApi.listAll({ limit: 20 })` to populate execution sidebar
- [ ] On `selectExec(e)`, call `loadDiffs(e.execution_id)` to populate diffs panel
- [ ] Map field names: `e.botName` -> `e.trigger_name`, `e.runAt` -> `e.started_at`, `e.filesChanged` -> `diffs.length`
- [ ] Drop the `comment` field from `DiffLine` (no backend source)

---

### Task 10: CrossTeamInsightsDashboard

**Files:**
- Create: `backend/app/db/cross_team_insights.py` — aggregation queries
- Create: `backend/app/routes/cross_team_insights.py` — `GET /admin/analytics/cross-team-insights`
- Modify: `backend/app/routes/__init__.py` — register blueprint
- Modify: `frontend/src/services/api/analytics.ts` — add `fetchCrossTeamInsights()`
- Modify: `frontend/src/views/CrossTeamInsightsDashboard.vue`

**Backend endpoint:**
- Single `GET /admin/analytics/cross-team-insights` returning all three sections: `{ teams, org_findings, top_risky_repos }`
- **Teams data** (from existing DB):
  - Reuse `get_all_teams()` for team list
  - Per-team execution counts: `SELECT COUNT(*) FROM execution_logs el JOIN triggers t ON el.trigger_id = t.id WHERE t.team_id = ?`
  - Success rate: `SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) / COUNT(*)`
  - Week-over-week: compare last 7 days vs prior 7 days
  - Most active trigger: `GROUP BY trigger_id ORDER BY COUNT(*) DESC LIMIT 1`
- **Findings/risk data**: Return `[]` / `0` with `data_available: false` flag (no real findings DB yet)

**Frontend wiring:**
- [ ] Add `analyticsApi.fetchCrossTeamInsights()` function
- [ ] Replace three hardcoded refs (`teams`, `orgFindings`, `topRiskyRepos`) with empty arrays
- [ ] Load all in `onMounted`; `orgTotals` computed auto-updates

---

### Task 11: ProjectHealthScorecardPage

**Files:**
- Create: `backend/app/services/project_health_service.py` — `ProjectHealthService.compute_scorecard(project_id)`
- Modify: `backend/app/routes/projects.py` — add `GET /<project_id>/health-scorecard`
- Create: `frontend/src/services/api/project-health.ts`
- Modify: `frontend/src/services/api/index.ts` — export `projectHealthApi`
- Modify: `frontend/src/views/ProjectHealthScorecardPage.vue`

**Backend endpoint:**
- `GET /admin/projects/<project_id>/health-scorecard` — returns `{ overall_score, trend_delta, weekly_history, categories, signals, recommendations, last_updated }`
- Computes from existing data:
  - `overall_score` + `weekly_history`: query `execution_logs` for success rate per week across last 8 weeks, normalize 0-100
  - `categories[pr-velocity]`: from `get_execution_summary(group_by='week')` filtered by project triggers
  - `categories[security]`: from `AuditService.get_stats()` severity totals
  - `categories[test-coverage]` + `categories[dependency-health]`: return `null` (no backing data)
  - `recommendations`: derived from signals (e.g. `critical_cve_count > 0` -> patch recommendation)

**Frontend wiring:**
- [ ] Create `projectHealthApi.getScorecard(projectId)` calling the endpoint
- [ ] Replace all hardcoded refs with empty/zero defaults
- [ ] Load `projects` via `projectApi.list()` in `onMounted`; load scorecard for first project
- [ ] Add `watch(selectedProjectId, loadScorecard)` to reload on project switch

---

### Task 12: PrReviewLearningLoopPage

**Files:**
- Modify: `backend/app/db/pr_reviews.py` — add `get_pr_review_learning_loop(trigger_id)`
- Modify: `backend/app/services/pr_review_service.py` — add `get_learning_loop()` static method
- Modify: `backend/app/routes/pr_reviews.py` — add `GET /learning-loop`
- Modify: `frontend/src/services/api/triggers.ts` — add `prReviewApi.getLearningLoop()`
- Modify: `frontend/src/views/PrReviewLearningLoopPage.vue`

**Backend endpoint:**
- `GET /api/pr-reviews/learning-loop` — derives signals from `pr_reviews` grouped by `project_name`:
  ```sql
  SELECT project_name AS pattern, COUNT(*) AS total,
    SUM(CASE WHEN review_status IN ('approved','fixed') THEN 1 ELSE 0 END) AS accepted_count,
    SUM(CASE WHEN review_status = 'changes_requested' THEN 1 ELSE 0 END) AS dismissed_count,
    SUM(CASE WHEN review_comment IS NOT NULL THEN 1 ELSE 0 END) AS commented_count,
    SUM(CASE WHEN fixes_applied > 0 THEN 1 ELSE 0 END) AS resolved_count,
    MAX(updated_at) AS last_seen
  FROM pr_reviews WHERE trigger_id = ? GROUP BY project_name
  ```
- Returns `{ signals: FindingSignal[], suggestions: RefinementSuggestion[] }`
- Suggestions derived server-side: suppress if `acceptRate < 0.25`, promote if `acceptRate > 0.85`
- `category` hardcoded to `'correctness'`; `trend` from comparing two 7-day windows

**Frontend wiring:**
- [ ] Add `prReviewApi.getLearningLoop()` to triggers API
- [ ] Replace hardcoded `signals` and `suggestions` with empty refs, populate in `onMounted`
- [ ] Keep `applySuggestion`/`dismissSuggestion` as client-only mutations (no DB persistence yet)

---

### Task 13: RepoBotDefaultsPage

**Files:**
- Create: `backend/app/routes/repo_bot_defaults.py` — CRUD endpoints
- Modify: `backend/app/routes/__init__.py` — register `repo_bot_defaults_bp`
- Create: `frontend/src/services/api/repo-bot-defaults.ts`
- Modify: `frontend/src/services/api/index.ts` — export
- Modify: `frontend/src/views/RepoBotDefaultsPage.vue`

**Backend endpoints:**
- `GET /admin/repo-bot-defaults` — fetches all triggers + their `project_paths` (github type), pivots from bot-centric to repo-centric view. Returns `{ bindings: [{ repo, bots, projectCount, enabled }], bots: AvailableBot[] }`
- `POST /admin/repo-bot-defaults` — body: `{ repo, bot_ids }`, calls `add_project_path` for each bot
- `PUT /admin/repo-bot-defaults/<repo_slug>` — body: `{ enabled }`, toggles all bound triggers
- `DELETE /admin/repo-bot-defaults/<repo_slug>` — removes github_repo_url path from all triggers
- Reuses existing `get_all_triggers()`, `list_project_paths()`, `add_project_path()`, `remove_project_path()`
- URL-safe repo slug: encode `owner/repo` as `owner__repo` or use query params

**Frontend wiring:**
- [ ] Create `repoBotDefaultsApi` with `list()`, `create()`, `toggleEnabled()`, `remove()`
- [ ] Replace hardcoded `bindings` and `availableBots` refs with empty arrays, populate in `onMounted`
- [ ] Wire `toggleEnabled`, `removeBinding`, `saveBinding` to API calls

---

### Task 14: SlackCommandGatewayPage

**Files:**
- Modify: `backend/app/routes/integrations.py` — add `GET /admin/integrations/slack/status`
- Create: `frontend/src/services/api/integrations.ts` — `slackApi`
- Modify: `frontend/src/views/SlackCommandGatewayPage.vue`

**Backend endpoint:**
- `GET /admin/integrations/slack/status` — queries `list_integrations(type="slack")`, returns first enabled record's `id`, `name` (workspace), `connected` (token non-empty)
- All other CRUD uses existing `PUT/POST/DELETE /admin/integrations/<id>`

**Frontend wiring:**
- [ ] Create `slackApi` with: `getStatus()`, `listCommands()` (GET integrations?type=slack), `createCommand()`, `updateCommand()`, `listCommandLogs()` (GET /api/audit/events/persistent?entity_type=integration&entity_id=slack)
- [ ] Replace hardcoded `slackConnected`, `workspace`, `commands`, `logs` refs
- [ ] Map integration fields: `config.command` -> `command`, `trigger_id` -> `botId`, `enabled` -> `enabled`
- [ ] Map audit event fields: `details.user_id` -> `user`, `details.channel_id` -> `channel`, `outcome` -> `status`
- [ ] `usageCount` defaults to `0` (no DB counter exists)

---

## Tier 3: New DB Tables + Full CRUD

These views require new database tables, migrations, CRUD functions, route endpoints, and frontend API modules.

---

### Task 15: FindingsTriageBoardPage

**Files:**
- Create: `backend/app/db/findings.py`
- Create: `backend/app/models/finding.py`
- Create: `backend/app/routes/findings.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/findings.ts`
- Modify: `frontend/src/services/api/index.ts`
- Modify: `frontend/src/views/FindingsTriageBoardPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    bot_id TEXT,
    file_ref TEXT,
    owner TEXT,
    execution_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_findings_status ON findings(status);
CREATE INDEX idx_findings_bot_id ON findings(bot_id);
```

**ID prefix:** `find-`

**DB functions** (`backend/app/db/findings.py`):
- `create_finding(data) -> str` — returns `find-XXXXXX` ID
- `list_findings(status=None, bot_id=None, owner=None) -> list[dict]`
- `get_finding(finding_id) -> dict | None`
- `update_finding(finding_id, updates) -> bool` — partial update (status, owner)
- `delete_finding(finding_id) -> bool`

**Pydantic models** (`backend/app/models/finding.py`):
- `FindingCreate` — `title`, `description`, `severity`, `bot_id`, `file_ref`, `owner`, `execution_id`
- `FindingUpdate` — `status?`, `owner?`

**Route endpoints:**
- `GET /api/findings` — query params: `status`, `bot_id`, `owner` -> `{ findings: [...] }`
- `POST /api/findings` -> `FindingResponse`
- `PATCH /api/findings/<finding_id>` -> `FindingResponse`
- `DELETE /api/findings/<finding_id>` -> 204

**Frontend wiring:**
- [ ] Create `findingsApi` with `list()`, `create()`, `update()`, `remove()`
- [ ] Name type `TriageFinding` to avoid collision with existing `Finding` type
- [ ] Replace hardcoded `findings` ref; populate via `onMounted`
- [ ] Wire `onDrop` (kanban drag) to `findingsApi.update(id, { status })` with optimistic update
- [ ] Wire `assignSelf` to `findingsApi.update(id, { owner: 'me' })`
- [ ] Wire `moveStatus` (drawer buttons) same as `onDrop`

---

### Task 16: BotMemoryStorePage

**Files:**
- Create: `backend/app/db/bot_memory.py`
- Create: `backend/app/routes/bot_memory.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/db/__init__.py`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/bot-memory.ts`
- Modify: `frontend/src/services/api/index.ts`
- Modify: `frontend/src/views/BotMemoryStorePage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS bot_memory (
    bot_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    expires_at TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bot_id, key)
);
```

**DB functions** (`backend/app/db/bot_memory.py`):
- `get_bot_memory(bot_id) -> list[dict]` — all entries + computed `used_bytes` (`sum(len(key)+len(value))`) and `max_bytes=65536`
- `upsert_memory_entry(bot_id, key, value, source, expires_at) -> dict`
- `delete_memory_entry(bot_id, key) -> bool`
- `clear_bot_memory(bot_id) -> bool`

**Route endpoints:**
- `GET /admin/bots/memory` — list all bots with memory (joins against triggers for names)
- `GET /admin/bots/<bot_id>/memory` — single bot memory
- `PUT /admin/bots/<bot_id>/memory/<key>` — upsert entry, body: `{ value, expiresAt? }`
- `DELETE /admin/bots/<bot_id>/memory/<key>` — delete one entry
- `DELETE /admin/bots/<bot_id>/memory` — clear all

**Frontend wiring:**
- [ ] Create `botMemoryApi` with `listAll()`, `upsertEntry()`, `deleteEntry()`, `clearAll()`
- [ ] Replace hardcoded `bots` ref; populate via `onMounted`
- [ ] Wire `saveEntry()` to `botMemoryApi.upsertEntry()`, `deleteEntry()` to API, `clearAllMemory()` to API
- [ ] Add `formatRelative(iso)` helper for `updatedAt` display

---

### Task 17: ExecutionTaggingPage

**Files:**
- Create: `backend/app/db/execution_tags.py`
- Create: `backend/app/routes/execution_tagging.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/execution-tagging.ts`
- Modify: `frontend/src/services/api/index.ts`
- Modify: `frontend/src/views/ExecutionTaggingPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS execution_tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT 'blue',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS execution_tag_assignments (
    tag_id TEXT NOT NULL REFERENCES execution_tags(id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL REFERENCES execution_logs(execution_id) ON DELETE CASCADE,
    PRIMARY KEY (tag_id, execution_id)
);
```

**ID prefix:** `etag-`

**DB functions** (`backend/app/db/execution_tags.py`):
- `list_tags() -> list[dict]` — with `COUNT(execution_id) AS execution_count`
- `create_tag(name, color) -> dict`
- `delete_tag(tag_id) -> bool`
- `add_tag_to_execution(tag_id, execution_id) -> bool`
- `remove_tag_from_execution(tag_id, execution_id) -> bool`
- `get_executions_with_tags(limit, offset, tag_ids=None) -> list[dict]` — joins execution_logs + aggregates tag IDs

**Route endpoints:**
- `GET /admin/execution-tags` — list all tags with execution_count
- `POST /admin/execution-tags` — create tag (`name`, `color`)
- `DELETE /admin/execution-tags/<tag_id>` — delete tag + assignments
- `GET /admin/execution-tagging` — list executions with `tags[]` array; `?tag_ids=t1,t2` filter
- `POST /admin/execution-tagging/<execution_id>/tags` — add tag (`{ tag_id }`)
- `DELETE /admin/execution-tagging/<execution_id>/tags/<tag_id>` — remove tag

**Frontend wiring:**
- [ ] Create `executionTaggingApi` with all 6 methods + `searchLogs(q)` (reuses existing `/admin/execution-search`)
- [ ] Replace hardcoded `tags` and `executions` refs; load both in `onMounted`
- [ ] Map response fields: `trigger_name` -> `botName`, `started_at` -> `triggeredAt`, `stdout_log[:200]` -> `logSnippet`
- [ ] Wire `createTag()`, `deleteTag()`, `addTagToExecution()`, `removeTagFromExecution()` to API calls

---

### Task 18: BotOutputPipingPage

**Files:**
- Create: `backend/app/db/bot_pipes.py`
- Create: `backend/app/routes/bot_pipes.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/bot-pipes.ts`
- Modify: `frontend/src/views/BotOutputPipingPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS bot_pipes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_bot_id TEXT NOT NULL,
    dest_bot_id TEXT NOT NULL,
    transform TEXT NOT NULL DEFAULT 'passthrough',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bot_pipe_executions (
    id TEXT PRIMARY KEY,
    pipe_id TEXT NOT NULL REFERENCES bot_pipes(id) ON DELETE CASCADE,
    pipe_name TEXT NOT NULL,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_preview TEXT,
    destination_status TEXT NOT NULL DEFAULT 'pending'
);
```

**ID prefix:** `pipe-`

**DB functions** (`backend/app/db/bot_pipes.py`):
- `get_all_pipes() -> list[dict]`
- `create_pipe(data) -> dict`
- `update_pipe(pipe_id, data) -> dict`
- `get_pipe_executions(limit=50) -> list[dict]`

**Route endpoints:**
- `GET /admin/bot-pipes` — list all pipes
- `POST /admin/bot-pipes` — create pipe
- `PATCH /admin/bot-pipes/<pipe_id>` — toggle/update
- `GET /admin/bot-pipes/executions` — list recent pipe executions

**Frontend wiring:**
- [ ] Create `pipeApi` with `list()`, `update()`, `listExecutions()`
- [ ] Replace static `pipes` and `executions` refs; load both in `onMounted` via `Promise.all`
- [ ] Wire `togglePipe()` to `pipeApi.update(pipe.id, { enabled: !pipe.enabled })`
- [ ] `transform` validated as `'passthrough' | 'trim' | 'json-extract'`

---

### Task 19: DataRetentionPoliciesPage

**Files:**
- Create: `backend/app/db/retention_policies.py`
- Create: `backend/app/models/retention.py`
- Create: `backend/app/routes/retention.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/db/ids.py`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/retention.ts`
- Modify: `frontend/src/services/api/index.ts`
- Modify: `frontend/src/views/DataRetentionPoliciesPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS retention_policies (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'global',
    scope_name TEXT NOT NULL DEFAULT 'All Teams',
    retention_days INTEGER NOT NULL DEFAULT 90,
    delete_on_expiry INTEGER NOT NULL DEFAULT 1,
    archive_on_expiry INTEGER NOT NULL DEFAULT 0,
    estimated_size_gb REAL NOT NULL DEFAULT 0.0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**ID prefix:** `rp-`

**DB functions** (`backend/app/db/retention_policies.py`):
- `list_policies() -> list[dict]`
- `create_policy(category, scope, scope_name, retention_days, delete_on_expiry, archive_on_expiry) -> str`
- `update_policy_enabled(policy_id, enabled) -> bool`
- `delete_policy(policy_id) -> bool`

**Route endpoints:**
- `GET /admin/retention-policies` -> list
- `POST /admin/retention-policies` -> create (201)
- `PATCH /admin/retention-policies/<policy_id>/toggle` -> toggle enabled
- `DELETE /admin/retention-policies/<policy_id>` -> delete
- `POST /admin/retention-policies/cleanup` -> stub (202, "Cleanup job queued")

**Frontend wiring:**
- [ ] Create `retentionApi` with `list()`, `create()`, `toggle()`, `delete()`, `runCleanup()`
- [ ] Replace static `policies` ref; populate via `onMounted`
- [ ] Wire `toggleEnabled()`, `deletePolicy()`, `runCleanup()`, `savePolicy()` to API calls

---

### Task 20: AgentQualityScoringPage

**Files:**
- Create: `backend/app/db/quality_ratings.py`
- Create: `backend/app/routes/quality_ratings.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/quality-ratings.ts`
- Modify: `frontend/src/services/api/index.ts`
- Modify: `frontend/src/views/AgentQualityScoringPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS execution_quality_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL UNIQUE,
    trigger_id TEXT,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    feedback TEXT DEFAULT '',
    rated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (execution_id) REFERENCES execution_logs(execution_id) ON DELETE CASCADE,
    FOREIGN KEY (trigger_id) REFERENCES triggers(id) ON DELETE SET NULL
);
```

**DB functions** (`backend/app/db/quality_ratings.py`):
- `upsert_quality_rating(execution_id, trigger_id, rating, feedback) -> dict` — INSERT OR REPLACE
- `get_quality_entries(trigger_id=None, limit=50, offset=0) -> list[dict]` — JOIN with execution_logs for `started_at`, `stdout_log[:120]` as preview
- `get_bot_quality_stats() -> list[dict]` — GROUP BY `trigger_id`: `AVG(rating)`, `COUNT(*)`, thumbsUp (`rating >= 4`), thumbsDown (`rating < 3`), `recentScores` (last 10)
- `trend`: compare avg of last 5 vs prior 5

**Route endpoints:**
- `GET /admin/quality/entries` — `?trigger_id=&limit=&offset=`
- `POST /admin/quality/entries/<execution_id>` — body: `{ rating, feedback }`
- `GET /admin/quality/stats` — returns `{ bots: BotQualityStats[] }`

**Frontend wiring:**
- [ ] Create `qualityApi` with `listEntries()`, `submitRating()`, `getStats()`
- [ ] Replace hardcoded `bots` and `entries` refs; load both in `onMounted` via `Promise.all`
- [ ] Wire `submitRating()` to call API before updating local state

---

### Task 21: OnboardingAutomationPage

**Files:**
- Create: `backend/app/db/onboarding.py`
- Create: `backend/app/routes/onboarding.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/db/triggers.py` — add `bot-onboarding` to `PREDEFINED_TRIGGERS`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/onboarding.ts`
- Modify: `frontend/src/services/api/index.ts`
- Modify: `frontend/src/views/OnboardingAutomationPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS onboarding_steps (
    id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL REFERENCES triggers(id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'custom',
    enabled INTEGER NOT NULL DEFAULT 1,
    delay_minutes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**ID prefix:** `step-`

**Seed predefined trigger** in `PREDEFINED_TRIGGERS`:
```python
{ "id": "bot-onboarding", "name": "New Engineer Onboarding", "trigger_source": "github",
  "match_field_value": "member", "backend_type": "claude", "is_predefined": 1 }
```

**DB functions** (`backend/app/db/onboarding.py`):
- `get_steps(trigger_id) -> list[dict]`
- `upsert_steps(trigger_id, steps: list[dict]) -> None` — DELETE + INSERT in one transaction

**Route endpoints:**
- `GET /admin/onboarding/config` — returns trigger record + its steps
- `PUT /admin/onboarding/config` — accepts `{ trigger_event, enabled, steps[] }`, updates trigger + replaces steps
- `GET /admin/onboarding/runs` — queries `execution_logs` for `trigger_id = 'bot-onboarding'`, returns last 20

**Frontend wiring:**
- [ ] Create `onboardingApi` with `getConfig()`, `saveConfig()`, `getRuns()`
- [ ] Replace static `steps` and `recentRuns` refs; load both in `onMounted` via `Promise.all`
- [ ] Wire `saveConfig()` to API call with snake_case -> camelCase mapping
- [ ] `completedSteps`/`totalSteps` in runs: return `total_steps` for success, `0` for failed

---

### Task 22: PrAutoAssignmentPage

**Files:**
- Create: `backend/app/db/pr_assignment.py`
- Create: `backend/app/routes/pr_assignment.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/__init__.py`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/pr-assignment.ts`
- Modify: `frontend/src/services/api/index.ts`
- Modify: `frontend/src/views/PrAutoAssignmentPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS pr_ownership_rules (
    id TEXT PRIMARY KEY,
    pattern TEXT NOT NULL,
    team TEXT NOT NULL,
    reviewers TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
```

**ID prefix:** `rule-`

**Note:** `reviewers` stored as comma-separated string, deserialized to `list[str]` in service layer.

**Settings** use existing `settings` table — keys: `pr_assignment_enabled`, `pr_assignment_min_confidence`, `pr_assignment_max_reviewers`

**DB functions** (`backend/app/db/pr_assignment.py`):
- `get_ownership_rules() -> list[dict]`
- `add_ownership_rule(pattern, team, reviewers, priority) -> str`
- `delete_ownership_rule(rule_id) -> bool`

**Route endpoints:**
- `GET /api/pr-assignment/rules` — list all rules
- `POST /api/pr-assignment/rules` — create rule
- `DELETE /api/pr-assignment/rules/<rule_id>` — delete
- `GET /api/pr-assignment/settings` — reads 3 settings keys
- `PUT /api/pr-assignment/settings` — writes 3 settings keys
- `GET /api/pr-assignment/recent` — maps from `pr_reviews` table: `pr_number`, `pr_title`, `assignedTo` (parsed from `review_comment`), `confidence` (heuristic from `fixes_applied`)

**Frontend wiring:**
- [ ] Create `prAssignmentApi` with `getRules()`, `addRule()`, `deleteRule()`, `getSettings()`, `saveSettings()`, `getRecent()`
- [ ] Replace hardcoded `rules`, `recentAssignments`, settings refs; load all in `onMounted` via `Promise.all`
- [ ] Wire `saveSettings()`, `addRule()`, `deleteRule()` to API calls

---

### Task 23: SkillVersionPinningPage

**Files:**
- Create: `backend/app/db/version_pins.py`
- Create: `backend/app/routes/version_pins.py`
- Modify: `backend/app/db/schema.py` or `backend/app/db/connection.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/db/seeds.py` — seed 5 pin rows + version history
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/version-pins.ts`
- Modify: `frontend/src/services/api/index.ts`
- Modify: `frontend/src/views/SkillVersionPinningPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS version_pins (
    id TEXT PRIMARY KEY,
    component_type TEXT NOT NULL,
    component_id TEXT NOT NULL,
    component_name TEXT NOT NULL,
    pinned_version TEXT,
    latest_version TEXT,
    bot_id TEXT,
    bot_name TEXT,
    status TEXT DEFAULT 'unpinned',
    pinned_at TEXT,
    changelog TEXT
);
CREATE TABLE IF NOT EXISTS component_version_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT NOT NULL,
    version TEXT NOT NULL,
    released_at TEXT,
    breaking INTEGER DEFAULT 0,
    summary TEXT
);
```

**ID prefix:** `vpin-`

**DB functions** (`backend/app/db/version_pins.py`):
- `get_all_version_pins() -> list[dict]`
- `update_pin_status(pin_id, pinned_version, status, pinned_at) -> bool`
- `set_pin_unpinned(pin_id) -> bool`
- `get_version_history(component_id) -> list[dict]`

**Route endpoints:**
- `GET /admin/version-pins/` — list all pins
- `PUT /admin/version-pins/<pin_id>` — update pin status/version
- `POST /admin/version-pins/<pin_id>/unpin` — set to unpinned
- `POST /admin/version-pins/upgrade-all` — batch upgrade outdated pins
- `GET /admin/version-pins/<component_id>/versions` — version history

**Frontend wiring:**
- [ ] Create `versionPinsApi` with `list()`, `updatePin()`, `unpin()`, `upgradeAll()`, `getVersionHistory()`
- [ ] Replace hardcoded `pins` and `availableVersions`; load via `onMounted`
- [ ] Cache version history per component: `watch(selectedPinId)` -> fetch if not cached
- [ ] Wire `applyPin()`, `unpin()`, `upgradeAll()` to API calls

---

### Task 24: RepoScopeFiltersPage

**Files:**
- Create: `backend/app/db/scope_filters.py`
- Create: `backend/app/routes/scope_filters.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/db/__init__.py`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/scope-filters.ts`
- Modify: `frontend/src/services/api/index.ts`
- Modify: `frontend/src/views/RepoScopeFiltersPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS scope_filters (
    id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL UNIQUE REFERENCES triggers(id) ON DELETE CASCADE,
    mode TEXT NOT NULL DEFAULT 'denylist',
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS scope_filter_patterns (
    id TEXT PRIMARY KEY,
    filter_id TEXT NOT NULL REFERENCES scope_filters(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    pattern TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_sfp_filter ON scope_filter_patterns(filter_id);
```

**ID prefixes:** `sf-` (filters), `spat-` (patterns)

**DB functions** (`backend/app/db/scope_filters.py`):
- `list_scope_filters() -> list[dict]`
- `get_scope_filter(filter_id) -> dict | None`
- `upsert_scope_filter(trigger_id, mode, enabled) -> str`
- `list_patterns(filter_id) -> list[dict]`
- `add_pattern(filter_id, type, pattern, description) -> str`
- `delete_pattern(pattern_id) -> bool`
- `update_scope_filter(filter_id, mode?, enabled?) -> bool`

**Route endpoints:**
- `GET /admin/scope-filters` — list all (joins trigger name for `botName`)
- `GET /admin/scope-filters/<filter_id>` — get with patterns
- `PUT /admin/scope-filters/<filter_id>` — update mode/enabled
- `POST /admin/scope-filters/<filter_id>/patterns` — add pattern
- `DELETE /admin/scope-filters/<filter_id>/patterns/<pattern_id>` — delete pattern

**Frontend wiring:**
- [ ] Create `scopeFiltersApi` with `list()`, `update()`, `addPattern()`, `deletePattern()`
- [ ] Replace hardcoded `filters` ref; populate via `onMounted`
- [ ] Wire `removePattern()`, `addPattern()`, `toggleFilter()`, `toggleMode()` to API calls
- [ ] `runTest` stays client-only (pure regex evaluation in browser)

---

### Task 25: VisualSkillComposerPage

**Files:**
- Create: `backend/app/db/skill_sets.py`
- Create: `backend/app/routes/skill_sets.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/db/ids.py` — add `generate_skill_set_id()`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/skill-sets.ts`
- Modify: `frontend/src/views/VisualSkillComposerPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS skill_sets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    skill_ids TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**ID prefix:** `sset-`

**Note:** `skill_ids` stored as JSON array string, deserialized in list/get endpoints.

**DB functions** (`backend/app/db/skill_sets.py`):
- `create_skill_set(name, skill_ids_json) -> str`
- `get_all_skill_sets() -> list[dict]`
- `get_skill_set(id) -> dict | None`
- `update_skill_set(id, name, skill_ids_json) -> bool`
- `delete_skill_set(id) -> bool`

**Route endpoints:**
- `GET /api/skill-sets/` — list all sets
- `POST /api/skill-sets/` — create (body: `{ name, skill_ids }`)
- `PUT /api/skill-sets/<set_id>` — update
- `DELETE /api/skill-sets/<set_id>` — delete

**Frontend wiring:**
- [ ] Create `skillSetsApi` with `list()`, `create()`, `update()`, `delete()`
- [ ] Available skills: load via existing `userSkillsApi.list()`, map `UserSkill` -> `Skill` (parse `metadata` JSON for `category` and `conflicts`)
- [ ] Replace hardcoded `availableSkills` and `composedSlots` refs
- [ ] Wire `saveComposition()`: `skillSetsApi.create()` on first save, `skillSetsApi.update()` on subsequent
- [ ] Track `savedSetId = ref<string | null>(null)` for create vs update logic

---

### Task 26: WebhookPayloadTransformerPage

**Files:**
- Create: `backend/app/db/payload_transformers.py`
- Create: `backend/app/routes/payload_transformers.py`
- Modify: `backend/app/db/schema.py`
- Modify: `backend/app/db/migrations.py`
- Modify: `backend/app/db/__init__.py`
- Modify: `backend/app/routes/__init__.py`
- Create: `frontend/src/services/api/payload-transformers.ts`
- Modify: `frontend/src/services/api/index.ts`
- Modify: `frontend/src/views/WebhookPayloadTransformerPage.vue`

**Table schema:**
```sql
CREATE TABLE IF NOT EXISTS payload_transformers (
    id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT 'default',
    rules TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**ID prefix:** `ptx-`

**Note:** `rules` stored as JSON blob of `TransformRule[]`. `trigger_id` can be `'global'` for the default (non-trigger-scoped) case.

**DB functions** (`backend/app/db/payload_transformers.py`):
- `get_transformer_by_trigger(trigger_id) -> dict | None`
- `upsert_transformer(trigger_id, name, rules_json) -> str`
- `delete_transformer(trigger_id) -> bool`

**Route endpoints:**
- `GET /admin/triggers/<trigger_id>/payload-transformer` — return rules (or `{ rules: [] }`)
- `PUT /admin/triggers/<trigger_id>/payload-transformer` — upsert rules
- `DELETE /admin/triggers/<trigger_id>/payload-transformer` — reset to empty

**Frontend wiring:**
- [ ] Create `payloadTransformerApi` with `get(triggerId)`, `save(triggerId, rules)`, `reset(triggerId)`
- [ ] Add `useRoute()` and read optional `triggerId` from `route.query` (fallback: `'global'`)
- [ ] In `onMounted`: load rules from API, fall back to existing default rules on error
- [ ] Add "Save Rules" button calling `payloadTransformerApi.save()`
- [ ] `runTransform()` stays client-side (no change)

---

### Task 27: GitHubActionsPage

**Files:**
- Modify: `frontend/src/views/GitHubActionsPage.vue`

**What to do:**

This is a documentation/config-generator page. The hardcoded `botId = ref('bot-security')` should be replaced with a dynamic bot selector loaded from the API.

- [ ] Import `triggerApi` from `../services/api`
- [ ] Add `triggers = ref<Array<{ id: string; name: string }>>([])` and `loading = ref(false)`
- [ ] In `onMounted`, call `triggerApi.list()` and populate `triggers`; default `botId` to first trigger's ID
- [ ] Replace the hardcoded `botId` input with a `<select>` bound to `botId` that lists all available triggers
- [ ] The `yamlSnippet` and `generatedWebhookUrl` computeds auto-update since they reference `botId.value`
- [ ] No backend changes needed — uses existing `GET /admin/triggers`
