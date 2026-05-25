<!--
  Memory System settings tab.

  Lists the bundled session-memory integrations wired into Agented's
  pipeline (Tesserae today; MemPalace / Cognee / others later). Each
  memory system has a status header (CLI installed? version?) + a
  per-project table where operators enable/disable + refresh.
-->
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import {
  memorySystemApi,
  type MemorySystemSummary,
  type TesseraeProjectState,
  type TesseraeWorkspaceStatus,
  type TesseraeAsyncJob,
} from '../../services/api/memory-system';
import { ApiError } from '../../services/api/client';
import { useToast } from '../../composables/useToast';
import LoadingState from '../base/LoadingState.vue';
import ErrorState from '../base/ErrorState.vue';

const showToast = useToast();

const isLoading = ref(true);
const loadError = ref<string | null>(null);
const memorySystems = ref<MemorySystemSummary[]>([]);
const tesseraeProjects = ref<TesseraeProjectState[]>([]);
const busyProjectId = ref<string | null>(null);

// Detail-panel + per-project Tesserae state
const expandedProjectId = ref<string | null>(null);
const projectStatus = ref<Record<string, TesseraeWorkspaceStatus>>({});
const runningJobs = ref<Record<string, TesseraeAsyncJob>>({});
const jobPollers = new Map<string, number>();

const tesserae = computed<MemorySystemSummary | null>(
  () => memorySystems.value.find((m) => m.id === 'tesserae') || null,
);

async function loadAll() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [a, b] = await Promise.all([
      memorySystemApi.list(),
      memorySystemApi.listTesseraeProjects(),
    ]);
    memorySystems.value = a.memory_systems || [];
    tesseraeProjects.value = b.projects || [];
  } catch (err) {
    loadError.value =
      err instanceof ApiError ? err.message : 'Failed to load memory systems';
  } finally {
    isLoading.value = false;
  }
}

async function toggleTesserae(project: TesseraeProjectState) {
  busyProjectId.value = project.project_id;
  try {
    const nextRoot = project.enabled
      ? null
      : (project.local_path || prompt(
          `Tesserae workspace path for ${project.project_name}`,
          project.local_path || '',
        ));
    if (project.enabled === false && !nextRoot) {
      // user cancelled the prompt
      return;
    }
    const res = await memorySystemApi.setTesseraeRoot(
      project.project_id, nextRoot,
    );
    // Replace the row in-place to avoid re-fetching.
    const idx = tesseraeProjects.value.findIndex(
      (p) => p.project_id === project.project_id,
    );
    if (idx >= 0) tesseraeProjects.value[idx] = res.project;
    showToast(
      res.project.enabled
        ? `Tesserae enabled for ${project.project_name}`
        : `Tesserae disabled for ${project.project_name}`,
      'success',
    );
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Toggle failed';
    showToast(msg, 'error');
  } finally {
    busyProjectId.value = null;
  }
}

async function refreshTesserae(project: TesseraeProjectState) {
  busyProjectId.value = project.project_id;
  try {
    const res = await memorySystemApi.refreshTesserae(project.project_id);
    if (res.skipped_reason) {
      showToast(
        `Refresh skipped: ${res.skipped_reason}`,
        res.skipped_reason === 'tesserae_disabled' ? 'info' : 'error',
      );
    } else {
      showToast(
        `Re-imported ${res.imported} sessions to ${project.project_name}`,
        'success',
      );
    }
    // Reload the row to pick up new manifest counts.
    const reload = await memorySystemApi.listTesseraeProjects();
    tesseraeProjects.value = reload.projects || [];
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Refresh failed';
    showToast(msg, 'error');
  } finally {
    busyProjectId.value = null;
  }
}

function fmtTimestamp(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function fmtBytes(n: number | null): string {
  if (!n) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

async function toggleDetails(project: TesseraeProjectState) {
  if (expandedProjectId.value === project.project_id) {
    expandedProjectId.value = null;
    return;
  }
  expandedProjectId.value = project.project_id;
  await refreshStatus(project.project_id);
}

async function refreshStatus(projectId: string) {
  try {
    const s = await memorySystemApi.tesseraeStatus(projectId);
    projectStatus.value = { ...projectStatus.value, [projectId]: s };
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Status fetch failed';
    showToast(msg, 'error');
  }
}

async function runInit(project: TesseraeProjectState) {
  busyProjectId.value = project.project_id;
  try {
    const r = await memorySystemApi.tesseraeInit(project.project_id);
    if (r.ok) {
      showToast(`Initialized Tesserae workspace for ${project.project_name}`, 'success');
    } else {
      showToast(`Init failed: ${r.reason || r.stderr || 'unknown'}`, 'error');
    }
    await Promise.all([
      refreshStatus(project.project_id),
      loadAll(),  // refresh the per-project row's workspace_initialized flag
    ]);
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Init failed';
    showToast(msg, 'error');
  } finally {
    busyProjectId.value = null;
  }
}

async function runIngest(project: TesseraeProjectState) {
  busyProjectId.value = project.project_id;
  try {
    const r = await memorySystemApi.tesseraeIngest(project.project_id);
    if (r.ok) {
      showToast(`Ingested docs (${r.elapsed_seconds?.toFixed(1)}s)`, 'success');
    } else {
      showToast(`Ingest failed: ${r.reason || r.stderr || 'unknown'}`, 'error');
    }
    await refreshStatus(project.project_id);
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Ingest failed';
    showToast(msg, 'error');
  } finally {
    busyProjectId.value = null;
  }
}

async function runCompile(project: TesseraeProjectState) {
  await startAsyncOp(project, 'compile', memorySystemApi.tesseraeCompile);
}

async function runBuildSite(project: TesseraeProjectState) {
  await startAsyncOp(project, 'build-site', memorySystemApi.tesseraeBuildSite);
}

async function startAsyncOp(
  project: TesseraeProjectState,
  opLabel: string,
  apiCall: (projectId: string) => Promise<TesseraeAsyncJob>,
) {
  busyProjectId.value = project.project_id;
  try {
    const job = await apiCall(project.project_id);
    runningJobs.value = { ...runningJobs.value, [project.project_id]: job };
    showToast(`${opLabel} started (${job.job_id})`, 'info');
    pollJob(project.project_id, job.job_id);
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : `${opLabel} failed to start`;
    showToast(msg, 'error');
  } finally {
    busyProjectId.value = null;
  }
}

function pollJob(projectId: string, jobId: string) {
  if (jobPollers.has(projectId)) {
    clearInterval(jobPollers.get(projectId));
  }
  const handle = window.setInterval(async () => {
    try {
      const job = await memorySystemApi.tesseraeJobStatus(jobId);
      runningJobs.value = { ...runningJobs.value, [projectId]: job };
      if (job.status !== 'running') {
        clearInterval(handle);
        jobPollers.delete(projectId);
        if (job.status === 'completed') {
          showToast(`${job.op} completed`, 'success');
        } else {
          showToast(
            `${job.op} failed: ${job.result?.reason || job.result?.stderr || 'unknown'}`,
            'error',
          );
        }
        refreshStatus(projectId);
        loadAll();
      }
    } catch (err) {
      clearInterval(handle);
      jobPollers.delete(projectId);
      const msg = err instanceof ApiError ? err.message : 'Polling failed';
      showToast(msg, 'error');
    }
  }, 3000);
  jobPollers.set(projectId, handle);
}

onUnmounted(() => {
  for (const h of jobPollers.values()) clearInterval(h);
  jobPollers.clear();
});

onMounted(loadAll);
</script>

<template>
  <section class="frameworks" data-testid="memory-system-settings">
    <header class="head">
      <h2>Memory System</h2>
      <p class="muted">
        Bundled session-memory integrations. Each memory system can
        be enabled per project; operators control when sessions get
        exported, when graphs get refreshed, and which workspaces are
        involved.
      </p>
    </header>

    <LoadingState v-if="isLoading" message="Loading frameworks…" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="loadAll" />

    <template v-else-if="tesserae">
      <!-- TESSERAE card -->
      <article class="framework" data-testid="memory-system-tesserae">
        <header class="framework__head">
          <div>
            <h3>{{ tesserae.name }}</h3>
            <p class="muted">{{ tesserae.summary }}</p>
          </div>
          <div class="status">
            <span
              class="badge"
              :class="tesserae.cli.installed ? 'ok' : 'warn'"
              :data-testid="`memory-system-tesserae-cli-${tesserae.cli.installed ? 'ok' : 'missing'}`"
            >
              CLI {{ tesserae.cli.installed ? 'installed' : 'missing' }}
            </span>
            <span v-if="tesserae.cli.version" class="meta">
              {{ tesserae.cli.version }}
            </span>
            <span class="meta">
              {{ tesserae.enabled_project_count }} enabled
            </span>
          </div>
        </header>

        <p v-if="!tesserae.cli.installed" class="hint warn">
          The <code>tesserae</code> CLI isn't on PATH. Install it
          first; per-project enable will still record the root, but
          imports will be silently skipped until the CLI is available.
        </p>

        <table class="projects" v-if="tesseraeProjects.length">
          <thead>
            <tr>
              <th>Project</th>
              <th>Workspace</th>
              <th>Sessions</th>
              <th>Last import</th>
              <th class="actions-col">Actions</th>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="p in tesseraeProjects"
              :key="p.project_id"
            >
              <tr
                :data-testid="`tesserae-project-row-${p.project_id}`"
                :data-enabled="p.enabled"
              >
                <td>
                  <button
                    v-if="p.enabled"
                    class="disclosure"
                    :class="{ open: expandedProjectId === p.project_id }"
                    :data-testid="`tesserae-disclosure-${p.project_id}`"
                    @click="toggleDetails(p)"
                  >▸</button>
                  <strong>{{ p.project_name }}</strong>
                  <div class="muted small"><code>{{ p.project_id }}</code></div>
                </td>
                <td>
                  <code v-if="p.tesserae_project_root">
                    {{ p.tesserae_project_root }}
                  </code>
                  <span v-else class="muted">—</span>
                  <span
                    v-if="p.enabled && !p.workspace_initialized"
                    class="badge warn inline"
                    :data-testid="`tesserae-project-uninit-${p.project_id}`"
                    title="Click ▸ to expand, then Init"
                  >
                    not initialized
                  </span>
                </td>
                <td>
                  <span v-if="p.session_count > 0">{{ p.session_count }}</span>
                  <span v-else class="muted">0</span>
                </td>
                <td class="meta">{{ fmtTimestamp(p.last_imported_at) }}</td>
                <td class="actions">
                  <button
                    class="btn"
                    :class="p.enabled ? 'btn-disable' : 'btn-enable'"
                    :disabled="busyProjectId === p.project_id"
                    :data-testid="`tesserae-toggle-${p.project_id}`"
                    @click="toggleTesserae(p)"
                  >
                    {{ p.enabled ? 'Disable' : 'Enable' }}
                  </button>
                  <button
                    class="btn btn-refresh"
                    :disabled="
                      !p.enabled
                      || !p.workspace_initialized
                      || busyProjectId === p.project_id
                    "
                    :data-testid="`tesserae-refresh-${p.project_id}`"
                    @click="refreshTesserae(p)"
                  >
                    Refresh
                  </button>
                </td>
              </tr>
              <tr
                v-if="expandedProjectId === p.project_id"
                class="detail-row"
                :data-testid="`tesserae-detail-${p.project_id}`"
              >
                <td colspan="5">
                  <div class="detail">
                    <!-- Status panel -->
                    <div class="status-panel">
                      <h4>Workspace status</h4>
                      <dl v-if="projectStatus[p.project_id]">
                        <dt>Initialized</dt>
                        <dd>
                          {{ projectStatus[p.project_id].workspace_initialized ? 'yes' : 'no' }}
                        </dd>
                        <dt>Graph compiled</dt>
                        <dd>
                          <span v-if="projectStatus[p.project_id].graph_compiled">
                            yes ({{ fmtBytes(projectStatus[p.project_id].graph_size_bytes) }})
                          </span>
                          <span v-else class="muted">no</span>
                        </dd>
                        <dt>Compiled at</dt>
                        <dd class="meta">
                          {{ fmtTimestamp(projectStatus[p.project_id].graph_compiled_at) }}
                        </dd>
                        <dt>Sessions imported</dt>
                        <dd>{{ projectStatus[p.project_id].session_count }}</dd>
                        <dt>Site built</dt>
                        <dd>
                          {{ projectStatus[p.project_id].site_built ? 'yes' : 'no' }}
                        </dd>
                      </dl>
                      <p v-else class="muted">Loading…</p>
                    </div>

                    <!-- Op buttons -->
                    <div class="ops">
                      <h4>Operations</h4>
                      <div class="op-grid">
                        <button
                          class="btn op-init"
                          :disabled="
                            !p.enabled
                            || busyProjectId === p.project_id
                            || p.workspace_initialized
                          "
                          :data-testid="`tesserae-op-init-${p.project_id}`"
                          @click="runInit(p)"
                        >
                          Init workspace
                        </button>
                        <button
                          class="btn op-ingest"
                          :disabled="
                            !p.enabled
                            || !p.workspace_initialized
                            || busyProjectId === p.project_id
                          "
                          :data-testid="`tesserae-op-ingest-${p.project_id}`"
                          @click="runIngest(p)"
                          title="Ingest README, CLAUDE.md, AGENTS.md, CONVENTIONS.md, .planning/ — whatever exists"
                        >
                          Ingest docs
                        </button>
                        <button
                          class="btn op-compile"
                          :disabled="
                            !p.enabled
                            || !p.workspace_initialized
                            || busyProjectId === p.project_id
                            || runningJobs[p.project_id]?.status === 'running'
                          "
                          :data-testid="`tesserae-op-compile-${p.project_id}`"
                          @click="runCompile(p)"
                          title="Extract typed knowledge graph from sources (heavy, async)"
                        >
                          Compile graph
                        </button>
                        <button
                          class="btn op-build"
                          :disabled="
                            !p.enabled
                            || !projectStatus[p.project_id]?.graph_compiled
                            || busyProjectId === p.project_id
                            || runningJobs[p.project_id]?.status === 'running'
                          "
                          :data-testid="`tesserae-op-build-site-${p.project_id}`"
                          @click="runBuildSite(p)"
                          title="Build static frontend site for the compiled graph"
                        >
                          Build site
                        </button>
                      </div>

                      <!-- Running job indicator -->
                      <div
                        v-if="runningJobs[p.project_id]"
                        class="job-status"
                        :data-status="runningJobs[p.project_id].status"
                        :data-testid="`tesserae-job-status-${p.project_id}`"
                      >
                        <strong>{{ runningJobs[p.project_id].op }}</strong>
                        — {{ runningJobs[p.project_id].status }}
                        <span
                          v-if="runningJobs[p.project_id].status === 'running'"
                          class="spinner"
                        >…</span>
                        <span
                          v-if="runningJobs[p.project_id].result?.elapsed_seconds"
                          class="meta"
                        >
                          ({{ runningJobs[p.project_id].result?.elapsed_seconds?.toFixed(1) }}s)
                        </span>
                      </div>

                      <p class="hint muted">
                        Auto-compile fires automatically every
                        <code>AGENTED_TESSERAE_AUTO_COMPILE_AFTER_N_SESSIONS</code>
                        session imports (default 5), with a min-interval
                        of
                        <code>AGENTED_TESSERAE_AUTO_COMPILE_MIN_INTERVAL_SECONDS</code>
                        (default 3600s).
                      </p>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <p v-else class="muted">
          No projects yet. Create one to enable per-project frameworks.
        </p>
      </article>
    </template>
  </section>
</template>

<style scoped>
.frameworks { display: flex; flex-direction: column; gap: 20px; }
.head h2 { font-size: 16px; margin: 0; }
.muted { color: var(--text-tertiary); font-size: 12px; margin: 4px 0 0; }
.small { font-size: 11px; }

.framework {
  border: 1px solid var(--border-default, rgba(255,255,255,0.1));
  border-radius: 10px;
  padding: 16px 18px;
  background: var(--bg-secondary, rgba(255,255,255,0.02));
  display: flex; flex-direction: column; gap: 14px;
}
.framework__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.framework__head h3 { font-size: 14px; margin: 0; }

.status { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.badge {
  font-size: 10px; padding: 2px 6px; border-radius: 3px;
  letter-spacing: 0.04em; text-transform: uppercase;
}
.badge.ok { background: var(--accent-green, #10b981); color: white; }
.badge.warn { background: var(--accent-amber, #f59e0b); color: white; }
.badge.inline { margin-left: 6px; }
.meta { font-size: 11px; color: var(--text-tertiary); font-variant-numeric: tabular-nums; }

.hint.warn {
  font-size: 12px; padding: 8px 10px; border-radius: 6px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: var(--text-secondary);
  margin: 0;
}

.projects { width: 100%; border-collapse: collapse; font-size: 12px; }
.projects th, .projects td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
  text-align: left; vertical-align: top;
}
.projects th {
  font-weight: 600; color: var(--text-tertiary);
  text-transform: uppercase; letter-spacing: 0.04em; font-size: 10px;
}
.actions-col { text-align: right; width: 1px; white-space: nowrap; }
.actions { text-align: right; white-space: nowrap; display: flex; gap: 6px; justify-content: flex-end; }

.btn {
  font-size: 11px; padding: 4px 10px; border-radius: 4px;
  border: 1px solid var(--border-default, rgba(255,255,255,0.12));
  background: var(--bg-secondary, transparent);
  color: var(--text-primary); cursor: pointer;
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-enable { border-color: var(--accent-green, #10b981); color: var(--accent-green, #10b981); }
.btn-disable { border-color: var(--accent-red, #ef4444); color: var(--accent-red, #ef4444); }
.btn-refresh { border-color: var(--accent-cyan, #06b6d4); color: var(--accent-cyan, #06b6d4); }

.disclosure {
  background: none; border: none;
  color: var(--text-tertiary); cursor: pointer;
  font-size: 11px; padding: 0 6px 0 0;
  transition: transform 0.15s;
  display: inline-block;
}
.disclosure.open { transform: rotate(90deg); }

.detail-row td { background: var(--bg-tertiary, rgba(255,255,255,0.02)); padding: 14px 18px; }
.detail {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 28px;
}
.status-panel h4, .ops h4 {
  font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--text-tertiary);
  margin: 0 0 8px;
}
.status-panel dl {
  display: grid; grid-template-columns: max-content 1fr;
  gap: 4px 12px; font-size: 12px; margin: 0;
}
.status-panel dt { color: var(--text-tertiary); }
.status-panel dd { margin: 0; }

.op-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px; margin-bottom: 12px;
}
.op-init    { border-color: var(--accent-amber, #f59e0b); color: var(--accent-amber, #f59e0b); }
.op-ingest  { border-color: var(--accent-cyan, #06b6d4); color: var(--accent-cyan, #06b6d4); }
.op-compile { border-color: var(--accent-purple, #8b5cf6); color: var(--accent-purple, #8b5cf6); }
.op-build   { border-color: var(--accent-green, #10b981); color: var(--accent-green, #10b981); }

.job-status {
  font-size: 12px; padding: 6px 10px; border-radius: 6px;
  background: rgba(139, 92, 246, 0.08);
  border: 1px solid rgba(139, 92, 246, 0.3);
  margin-bottom: 8px;
}
.job-status[data-status="completed"] {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.3);
}
.job-status[data-status="failed"] {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.3);
}
.spinner { display: inline-block; animation: dots 1.4s infinite; }
@keyframes dots {
  0%, 20%   { opacity: 0.2; }
  50%       { opacity: 1; }
  80%, 100% { opacity: 0.2; }
}

code { font-family: var(--font-mono, monospace); font-size: 11px; }
</style>
