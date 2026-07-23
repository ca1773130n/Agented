<script setup lang="ts">
/**
 * SuperAgentMemoryPanel — Layered Memory (Tesserae 0.21.0).
 *
 * Surfaces a super-agent's own layered knowledge graph on the inspector
 * page: its org position (parent + direct reports, derived from the
 * project agent org), its distilled L1 runbook notes, and a "Distill
 * now" control that rebuilds L1 + the L2' manager rollup.
 *
 * projectId sourcing: the inspector page has no project context of its
 * own, so the panel accepts an optional ``projectId`` prop and, when
 * absent, renders an inline note + a project picker (``projectApi.list``)
 * to let the operator choose which project's agent org to read.
 */
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  getSuperAgentMemory,
  distillSuperAgentMemory,
  drillSuperAgentMemory,
  projectApi,
} from '../../services/api';
import type {
  SuperAgentMemory,
  SuperAgentDrillResult,
  AgentOrgRow,
  Project,
} from '../../services/api';

const { t } = useI18n();

const props = defineProps<{
  superAgentId: string;
  /** Pre-selected project. When absent the panel renders a picker. */
  projectId?: string;
}>();

const selectedProjectId = ref<string>(props.projectId ?? '');
const memory = ref<SuperAgentMemory | null>(null);
const org = ref<AgentOrgRow[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const distilling = ref(false);
const distillNote = ref<string | null>(null);

// node_id → drilled L0 evidence (or 'loading'). One shared map across all notes;
// clicking a ref toggles its evidence open/closed (Tesserae 0.22 `agents drill`).
const drills = ref<Record<string, SuperAgentDrillResult | 'loading'>>({});

function drillText(nodeId: string): string {
  const d = drills.value[nodeId];
  if (!d || d === 'loading') return '';
  return d.ok ? d.text ?? '' : t('superAgentMemory.drillFailed');
}

async function drill(nodeId: string) {
  if (!hasProject.value) return;
  const cur = drills.value[nodeId];
  if (cur === 'loading') return;
  if (cur) {
    // Already open → toggle closed.
    const next = { ...drills.value };
    delete next[nodeId];
    drills.value = next;
    return;
  }
  // Capture the context this drill was issued for; a switch mid-flight clears
  // `drills` (the watch), so we must NOT repopulate it with the prior
  // project's/agent's evidence — wrong provenance in an audit view. Mirrors
  // the stale-response guard in load().
  const requestedProject = selectedProjectId.value;
  const requestedSa = props.superAgentId;
  const stale = () =>
    requestedProject !== selectedProjectId.value || requestedSa !== props.superAgentId;
  drills.value = { ...drills.value, [nodeId]: 'loading' };
  try {
    const res = await drillSuperAgentMemory(requestedSa, requestedProject, nodeId);
    if (stale()) return;
    drills.value = { ...drills.value, [nodeId]: res };
  } catch (e: unknown) {
    if (stale()) return;
    drills.value = {
      ...drills.value,
      [nodeId]: { ok: false, reason: e instanceof Error ? e.message : String(e) },
    };
  }
}

const projects = ref<Project[]>([]);
const projectsLoading = ref(false);

const hasProject = computed(() => selectedProjectId.value.length > 0);

// This SA's parent org row (resolved via memory.key → its parent key).
const parentRow = computed<AgentOrgRow | null>(() => {
  if (!memory.value) return null;
  const self = org.value.find((r) => r.key === memory.value!.key);
  if (!self || !self.parent) return null;
  return org.value.find((r) => r.key === self.parent) ?? null;
});

// Direct reports: org rows whose parent is this SA's key.
const directReports = computed<AgentOrgRow[]>(() => {
  if (!memory.value) return [];
  return org.value.filter((r) => r.parent === memory.value!.key);
});

async function loadProjects() {
  projectsLoading.value = true;
  try {
    const res = await projectApi.list({ limit: 200 });
    projects.value = res.projects;
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    projectsLoading.value = false;
  }
}

async function load() {
  if (!hasProject.value) return;
  loading.value = true;
  error.value = null;
  const requestedProject = selectedProjectId.value;
  const requestedSa = props.superAgentId;
  try {
    const res = await getSuperAgentMemory(requestedSa, requestedProject);
    // Guard against a stale in-flight response clobbering newer state.
    if (requestedProject !== selectedProjectId.value || requestedSa !== props.superAgentId) {
      return;
    }
    memory.value = res.memory;
    org.value = res.org;
  } catch (e: unknown) {
    if (requestedProject !== selectedProjectId.value || requestedSa !== props.superAgentId) {
      return;
    }
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (requestedProject === selectedProjectId.value && requestedSa === props.superAgentId) {
      loading.value = false;
    }
  }
}

async function distill() {
  if (!hasProject.value || distilling.value) return;
  distilling.value = true;
  distillNote.value = null;
  error.value = null;
  try {
    await distillSuperAgentMemory(props.superAgentId, selectedProjectId.value);
    distillNote.value = t('superAgentMemory.distilling');
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    distilling.value = false;
  }
}

watch(
  () => [props.superAgentId, selectedProjectId.value] as const,
  () => {
    memory.value = null;
    org.value = [];
    distillNote.value = null;
    drills.value = {};
    if (hasProject.value) load();
  },
);

watch(
  () => props.projectId,
  (next) => {
    if (next != null && next !== selectedProjectId.value) {
      selectedProjectId.value = next;
    }
  },
);

onMounted(() => {
  if (hasProject.value) {
    load();
  } else {
    loadProjects();
  }
});
</script>

<template>
  <article class="sa-memory" data-testid="sa-memory-panel">
    <header class="sa-memory__head">
      <h2 class="sa-memory__title">{{ t('superAgentMemory.title') }}</h2>
      <button
        v-if="hasProject"
        type="button"
        class="sa-memory__distill"
        data-testid="sa-memory-distill"
        :disabled="distilling"
        @click="distill()"
      >
        {{ distilling ? t('superAgentMemory.distilling') : t('superAgentMemory.distillNow') }}
      </button>
    </header>

    <!-- No project context: inline note + picker. -->
    <div v-if="!hasProject" class="sa-memory__picker" data-testid="sa-memory-picker">
      <p class="sa-memory__note">{{ t('superAgentMemory.selectProject') }}</p>
      <select
        class="sa-memory__select"
        data-testid="sa-memory-project-select"
        :disabled="projectsLoading"
        @change="selectedProjectId = ($event.target as HTMLSelectElement).value"
      >
        <option value="">{{ t('superAgentMemory.selectProjectOption') }}</option>
        <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
    </div>

    <template v-else>
      <div v-if="loading" class="sa-memory__state" data-testid="sa-memory-loading">
        {{ t('superAgentMemory.loading') }}
      </div>
      <div v-else-if="error" class="sa-memory__error" data-testid="sa-memory-error">
        {{ error }}
        <button type="button" @click="load()">{{ t('superAgentMemory.retry') }}</button>
      </div>

      <template v-else-if="memory">
        <p v-if="distillNote" class="sa-memory__distill-note" data-testid="sa-memory-distill-note">
          {{ distillNote }}
        </p>

        <!-- Org position -->
        <section class="sa-memory__org" data-testid="sa-memory-org">
          <div class="sa-memory__org-row">
            <span class="sa-memory__org-label">{{ t('superAgentMemory.reportsTo') }}</span>
            <span class="sa-memory__org-value" data-testid="sa-memory-parent">
              {{ parentRow ? parentRow.label : t('superAgentMemory.noParent') }}
            </span>
          </div>
          <div class="sa-memory__org-row sa-memory__org-row--reports">
            <span class="sa-memory__org-label">{{ t('superAgentMemory.directReports') }}</span>
            <ul
              v-if="directReports.length"
              class="sa-memory__reports"
              data-testid="sa-memory-reports"
            >
              <li v-for="r in directReports" :key="r.key" class="sa-memory__report">
                <span class="sa-memory__report-label">{{ r.label }}</span>
                <span class="sa-memory__report-sessions">
                  {{ r.sessions }} {{ t('superAgentMemory.sessions') }}
                </span>
              </li>
            </ul>
            <span v-else class="sa-memory__org-value">{{ t('superAgentMemory.noReports') }}</span>
          </div>
        </section>

        <!-- Distilled runbook -->
        <section class="sa-memory__runbook" data-testid="sa-memory-runbook">
          <h3 class="sa-memory__subtitle">{{ t('superAgentMemory.distilledRunbook') }}</h3>
          <div
            v-if="memory.notes.length === 0"
            class="sa-memory__empty"
            data-testid="sa-memory-empty"
          >
            {{ t('superAgentMemory.emptyRunbook') }}
          </div>
          <ol v-else class="sa-memory__notes">
            <li
              v-for="(note, i) in memory.notes"
              :key="i"
              class="sa-memory__note-item"
              :data-testid="`sa-memory-note-${i}`"
            >
              <h4 class="sa-memory__note-title">{{ note.title }}</h4>
              <p class="sa-memory__note-body">{{ note.body }}</p>
              <!-- L0 evidence drill-down (Tesserae 0.22 `agents drill`). -->
              <div
                v-if="note.refs && note.refs.length"
                class="sa-memory__refs"
                :data-testid="`sa-memory-refs-${i}`"
              >
                <div v-for="ref in note.refs" :key="ref" class="sa-memory__ref-row">
                  <button
                    type="button"
                    class="sa-memory__ref"
                    :disabled="drills[ref] === 'loading'"
                    @click="drill(ref)"
                  >
                    {{ drills[ref] === 'loading' ? t('superAgentMemory.drilling') : ref }}
                  </button>
                  <!-- Untrusted evidence text — {{ }} escapes it; never v-html. -->
                  <pre
                    v-if="drills[ref] && drills[ref] !== 'loading'"
                    class="sa-memory__drill"
                  >{{ drillText(ref) }}</pre>
                </div>
              </div>
            </li>
          </ol>
        </section>
      </template>
    </template>
  </article>
</template>

<style scoped>
.sa-memory {
  background: var(--bg-secondary, #1a1a20);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.sa-memory__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.sa-memory__title {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary, #fff);
}
.sa-memory__distill {
  background: transparent;
  border: 1px solid var(--accent-violet, #8855ff);
  color: var(--accent-violet, #8855ff);
  border-radius: 4px;
  padding: 4px 12px;
  font-size: 11px;
  cursor: pointer;
}
.sa-memory__distill:hover:not(:disabled) {
  background: rgba(136, 85, 255, 0.12);
}
.sa-memory__distill:disabled {
  opacity: 0.6;
  cursor: default;
}
.sa-memory__picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sa-memory__note {
  margin: 0;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
  font-size: 12px;
}
.sa-memory__select {
  padding: 6px 8px;
  background: var(--bg-primary, #101015);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 4px;
  color: var(--text-primary, #fff);
  font-size: 12px;
  max-width: 320px;
}
.sa-memory__state,
.sa-memory__empty {
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
  font-size: 12px;
  padding: 8px 4px;
}
.sa-memory__error {
  color: var(--accent-red, #ff5470);
  font-size: 12px;
  padding: 8px 4px;
}
.sa-memory__error button {
  margin-left: 12px;
  padding: 2px 10px;
  background: transparent;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 4px;
  color: inherit;
  cursor: pointer;
}
.sa-memory__distill-note {
  margin: 0 0 12px;
  color: var(--accent-violet, #8855ff);
  font-size: 12px;
}
.sa-memory__org {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-primary, #101015);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 6px;
  margin-bottom: 14px;
}
.sa-memory__org-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 12px;
}
.sa-memory__org-row--reports {
  align-items: flex-start;
}
.sa-memory__org-label {
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
  min-width: 110px;
  flex-shrink: 0;
}
.sa-memory__org-value {
  color: var(--text-secondary, rgba(255, 255, 255, 0.7));
}
.sa-memory__reports {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.sa-memory__report {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 2px 8px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 999px;
  background: var(--bg-secondary, #1a1a20);
}
.sa-memory__report-label {
  color: var(--text-primary, #fff);
  font-size: 12px;
}
.sa-memory__report-sessions {
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
  font-size: 11px;
}
.sa-memory__subtitle {
  margin: 0 0 8px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
}
.sa-memory__notes {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sa-memory__note-item {
  padding: 10px 12px;
  background: var(--bg-primary, #101015);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 6px;
}
.sa-memory__note-title {
  margin: 0 0 4px;
  font-size: 13px;
  color: var(--text-primary, #fff);
}
.sa-memory__note-body {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary, rgba(255, 255, 255, 0.7));
  white-space: pre-wrap;
  word-break: break-word;
}
.sa-memory__refs {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}
.sa-memory__ref {
  align-self: flex-start;
  background: transparent;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
  cursor: pointer;
}
.sa-memory__ref:hover:not(:disabled) {
  color: var(--accent-violet, #8855ff);
  border-color: var(--accent-violet, #8855ff);
}
.sa-memory__ref:disabled {
  opacity: 0.6;
  cursor: default;
}
.sa-memory__drill {
  margin: 4px 0 0;
  padding: 8px 10px;
  background: var(--bg-secondary, #1a1a20);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary, rgba(255, 255, 255, 0.7));
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}
</style>
