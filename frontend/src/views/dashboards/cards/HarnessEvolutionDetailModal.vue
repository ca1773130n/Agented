<!--
  HarnessEvolutionDetailModal — full per-entry payload view for one
  project-scoped Forge evolution round. Renders rule/hook/command/mcp_server
  patch entries (skill entries surface as read-only diagnostic info).
-->
<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import {
  EVOLUTION_STATUS_COLOR_VAR,
  EVOLUTION_STATUS_LABEL,
  FORGE_KIND_COLOR_VAR,
  harnessEvolutionApi,
  type EvolutionImpactResponse,
  type EvolutionRound,
} from '../../../services/api/harness-evolution';

const props = defineProps<{ round: EvolutionRound | null }>();
const emit = defineEmits<{
  close: [];
  approve: [roundId: string];
  abort: [roundId: string];
}>();

const impact = ref<EvolutionImpactResponse | null>(null);
const impactLoading = ref(false);
const impactError = ref<string | null>(null);

const isOpen = computed(() => props.round !== null);
const entries = computed(() => props.round?.output_patch?.entries || []);

async function loadImpact() {
  impact.value = null;
  impactError.value = null;
  if (!props.round || props.round.status !== 'applied') return;
  impactLoading.value = true;
  try {
    impact.value = await harnessEvolutionApi.getImpact(props.round.id);
  } catch (err) {
    impactError.value =
      err instanceof Error ? err.message : 'Failed to load impact';
  } finally {
    impactLoading.value = false;
  }
}

watch(() => props.round?.id, () => {
  if (props.round) loadImpact();
});

onMounted(() => {
  if (props.round) loadImpact();
});

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

function fmtDelta(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  const sign = v > 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(1)}pp`;
}

function close() { emit('close'); }
function onBackdropClick(event: MouseEvent) {
  if ((event.target as HTMLElement).classList.contains('modal-backdrop')) close();
}
function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') close();
}
</script>

<template>
  <div
    v-if="isOpen"
    class="modal-backdrop"
    data-testid="evolution-detail-modal"
    @click="onBackdropClick"
    @keydown="onKeydown"
    tabindex="-1"
  >
    <div class="modal-panel" role="dialog" aria-modal="true">
      <header class="modal-head">
        <div class="modal-head__left">
          <span
            class="modal-pill"
            :style="{ background: EVOLUTION_STATUS_COLOR_VAR[round!.status] }"
          >{{ EVOLUTION_STATUS_LABEL[round!.status] }}</span>
          <code class="modal-project">{{ round!.project_id }}</code>
        </div>
        <button
          class="modal-close"
          data-testid="evolution-detail-close"
          aria-label="Close"
          @click="close"
        >×</button>
      </header>

      <div class="modal-body">
        <section class="meta">
          <div><label>Round</label><code>{{ round!.id }}</code></div>
          <div><label>Started</label><span>{{ round!.started_at }}</span></div>
          <div v-if="round!.finished_at">
            <label>Finished</label><span>{{ round!.finished_at }}</span>
          </div>
          <div>
            <label>Inputs</label>
            <span>{{ round!.input_execution_count }} trajectories</span>
          </div>
        </section>

        <section v-if="round!.notes" class="notes">
          <h3>Codex notes</h3>
          <pre data-testid="evolution-detail-notes">{{ round!.notes }}</pre>
        </section>

        <section v-if="round!.error_message" class="error">
          <h3>Error</h3>
          <pre data-testid="evolution-detail-error">{{ round!.error_message }}</pre>
        </section>

        <section class="entries">
          <h3>Forge patch entries ({{ entries.length }})</h3>
          <p v-if="entries.length === 0" class="muted">No changes proposed.</p>
          <ul v-else>
            <li
              v-for="(e, i) in entries"
              :key="`${e.kind}-${e.name}-${i}`"
              class="entry"
              :data-testid="`evolution-entry-${i}`"
            >
              <header class="entry__head">
                <span class="entry__op" :data-op="e.op">{{ e.op }}</span>
                <span
                  class="entry__kind"
                  :style="{ borderColor: FORGE_KIND_COLOR_VAR[e.kind] }"
                >{{ e.kind }}</span>
                <span class="entry__name">{{ e.name }}</span>
                <code v-if="e.existing_asset_id" class="entry__id">
                  #{{ e.existing_asset_id }}
                </code>
              </header>
              <pre v-if="e.payload" class="entry__payload">{{ JSON.stringify(e.payload, null, 2) }}</pre>
            </li>
          </ul>
        </section>

        <section
          v-if="round!.status === 'applied'"
          class="impact"
          data-testid="evolution-impact-section"
        >
          <h3>Impact</h3>
          <p v-if="impactLoading" class="muted">Computing…</p>
          <p v-else-if="impactError" class="error-text">{{ impactError }}</p>
          <template v-else-if="impact && impact.available">
            <div class="impact-grid">
              <div class="impact-col">
                <label>Before</label>
                <span class="impact-val">{{ fmtPct(impact.before.success_rate) }}</span>
                <span class="impact-meta">{{ impact.before.executions }} runs</span>
              </div>
              <div class="impact-col">
                <label>After</label>
                <span class="impact-val">{{ fmtPct(impact.after.success_rate) }}</span>
                <span class="impact-meta">{{ impact.after.executions }} runs</span>
              </div>
              <div class="impact-col">
                <label>Δ Success</label>
                <span
                  class="impact-val"
                  :class="{
                    pos: (impact.delta.success_rate || 0) > 0,
                    neg: (impact.delta.success_rate || 0) < 0,
                  }"
                  data-testid="evolution-impact-delta"
                >{{ fmtDelta(impact.delta.success_rate) }}</span>
              </div>
            </div>
          </template>
          <p v-else-if="impact && !impact.available" class="muted">
            {{ impact.reason }}
          </p>
        </section>

        <section v-if="round!.status === 'awaiting_approval'" class="actions">
          <button
            class="btn btn-approve"
            data-testid="evolution-detail-approve"
            @click="emit('approve', round!.id)"
          >Approve</button>
          <button
            class="btn btn-abort"
            data-testid="evolution-detail-abort"
            @click="emit('abort', round!.id)"
          >Abort</button>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex; align-items: center; justify-content: center;
  z-index: 100; padding: 24px;
}
.modal-panel {
  background: var(--bg-primary, #111);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.12));
  border-radius: 10px;
  max-width: 720px; width: 100%; max-height: 85vh;
  display: flex; flex-direction: column;
}
.modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
}
.modal-head__left { display: flex; align-items: center; gap: 10px; }
.modal-pill { font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; color: white; letter-spacing: 0.04em; }
.modal-project { font-family: var(--font-mono, monospace); font-size: 13px; color: var(--text-secondary); }
.modal-close {
  background: transparent; border: none;
  color: var(--text-tertiary); font-size: 22px;
  cursor: pointer; line-height: 1;
}
.modal-body { overflow-y: auto; padding: 16px 18px; display: flex; flex-direction: column; gap: 16px; }
.modal-body h3 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-tertiary); margin: 0 0 8px; }

.meta { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 16px; font-size: 12px; }
.meta label { font-size: 10px; text-transform: uppercase; color: var(--text-tertiary); display: block; }
.meta code { font-family: var(--font-mono, monospace); }

.notes pre,
.error pre {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
  padding: 10px; font-size: 11px; border-radius: 6px;
  white-space: pre-wrap; margin: 0; max-height: 140px; overflow-y: auto;
}
.error pre { color: var(--accent-red, #ef4444); }

.entries ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.entry {
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 6px; padding: 8px 10px;
}
.entry__head { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.entry__op {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  padding: 1px 5px; border-radius: 3px; letter-spacing: 0.04em;
  color: white; background: var(--text-tertiary, #6b7280);
}
.entry__op[data-op='create'] { background: var(--accent-green,  #10b981); }
.entry__op[data-op='update'] { background: var(--accent-cyan,   #06b6d4); }
.entry__op[data-op='delete'] { background: var(--accent-red,    #ef4444); }
.entry__kind {
  font-size: 10px; padding: 1px 5px;
  border-radius: 3px;
  border: 1px solid var(--text-tertiary, #6b7280);
  color: var(--text-secondary);
}
.entry__name { font-size: 12px; color: var(--text-primary); }
.entry__id { font-family: var(--font-mono, monospace); font-size: 10px; color: var(--text-tertiary); }
.entry__payload {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
  padding: 8px; margin: 6px 0 0; border-radius: 4px;
  font-size: 11px; max-height: 200px; overflow-y: auto;
  white-space: pre-wrap;
}

.impact-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.impact-col { display: flex; flex-direction: column; gap: 2px; }
.impact-col label { font-size: 10px; text-transform: uppercase; color: var(--text-tertiary); }
.impact-val { font-size: 18px; font-weight: 600; }
.impact-val.pos { color: var(--accent-green, #10b981); }
.impact-val.neg { color: var(--accent-red, #ef4444); }
.impact-meta { font-size: 10px; color: var(--text-tertiary); }

.actions { display: flex; gap: 10px; justify-content: flex-end; padding-top: 8px; }
.btn {
  font-size: 12px; padding: 6px 14px; border-radius: 4px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.12));
  background: var(--bg-secondary, transparent);
  color: var(--text-primary); cursor: pointer;
}
.btn-approve { border-color: var(--accent-green, #10b981); color: var(--accent-green, #10b981); }
.btn-abort { border-color: var(--accent-red, #ef4444); color: var(--accent-red, #ef4444); }

.muted { font-size: 12px; color: var(--text-tertiary); margin: 0; }
.error-text { font-size: 12px; color: var(--accent-red, #ef4444); margin: 0; }
</style>
