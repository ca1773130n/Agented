<!--
  Memory System settings tab.

  Lists the bundled session-memory integrations wired into Agented's
  pipeline (Tesserae today; MemPalace / Cognee / others later). Each
  memory system has a status header (CLI installed? version?) + a
  per-project table where operators enable/disable + refresh.
-->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  memorySystemApi,
  type MemorySystemSummary,
  type TesseraeProjectState,
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
            <tr
              v-for="p in tesseraeProjects"
              :key="p.project_id"
              :data-testid="`tesserae-project-row-${p.project_id}`"
              :data-enabled="p.enabled"
            >
              <td>
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
                  title="Run `tesserae project init` in this directory"
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

code { font-family: var(--font-mono, monospace); font-size: 11px; }
</style>
