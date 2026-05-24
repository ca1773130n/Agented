<!--
  HarnessEvolutionCard — Activity-lane card surfacing T3 evolution rounds.

  Lists the most recent rounds across all bots, colour-coded by status.
  For ``awaiting_approval`` rounds, exposes inline Approve / Abort buttons
  so an operator can act without dropping to the CLI.

  Reference: arXiv 2605.22166 (Life-Harness §5.2 Evolution Dynamics).
-->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  EVOLUTION_STATUS_COLOR_VAR,
  EVOLUTION_STATUS_LABEL,
  harnessEvolutionApi,
  type EvolutionRound,
} from '../../../services/api/harness-evolution';
import { triggerApi } from '../../../services/api';
import type { Trigger } from '../../../services/api/types/triggers';
import LoadingState from '../../../components/base/LoadingState.vue';
import ErrorState from '../../../components/base/ErrorState.vue';
import HarnessEvolutionDetailModal from './HarnessEvolutionDetailModal.vue';

const emit = defineEmits<{ loaded: [slug: string] }>();

const isLoading = ref(false);
const loadError = ref<string | null>(null);
const rounds = ref<EvolutionRound[]>([]);
const actingRoundId = ref<string | null>(null);
const actionError = ref<string | null>(null);

// Trigger form state. Only dry-run is exposed from the UI; live (auto-apply)
// stays CLI-only so accidental clicks can't bypass the approval surface.
const bots = ref<Trigger[]>([]);
const selectedBotId = ref<string>('');
const triggering = ref(false);
const triggerStatus = ref<string | null>(null);
const triggerError = ref<string | null>(null);

const detailRound = ref<EvolutionRound | null>(null);

function openDetail(round: EvolutionRound) {
  detailRound.value = round;
}

function closeDetail() {
  detailRound.value = null;
}

async function approveFromDetail(roundId: string) {
  closeDetail();
  const target = rounds.value.find((r) => r.id === roundId);
  if (target) await approve(target);
}

async function abortFromDetail(roundId: string) {
  closeDetail();
  const target = rounds.value.find((r) => r.id === roundId);
  if (target) await abort(target);
}

const isEmpty = computed(() => rounds.value.length === 0);
const canTrigger = computed(
  () => !triggering.value && !!selectedBotId.value,
);

async function loadData() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [roundsRes, botsRes] = await Promise.all([
      harnessEvolutionApi.listAll({ limit: 10 }),
      triggerApi.list().catch(() => ({ triggers: [] as Trigger[] })),
    ]);
    rounds.value = roundsRes?.rounds || [];
    bots.value = botsRes?.triggers || [];
    if (!selectedBotId.value && bots.value.length > 0) {
      selectedBotId.value = bots.value[0].id;
    }
  } catch (err) {
    loadError.value =
      err instanceof Error ? err.message : 'Failed to load evolution rounds';
    rounds.value = [];
  } finally {
    isLoading.value = false;
    emit('loaded', 'harness-evolution');
  }
}

async function runDryRun() {
  if (!canTrigger.value) return;
  triggering.value = true;
  triggerError.value = null;
  triggerStatus.value = null;
  try {
    const result = await harnessEvolutionApi.dryRun(selectedBotId.value, {
      limit: 25,
    });
    triggerStatus.value =
      `Round ${result.round_id} · ${result.status}` +
      (result.error ? ` · ${result.error}` : '');
    if (result.status === 'failed') {
      triggerError.value = result.error || 'Dry-run failed';
    }
  } catch (err) {
    triggerError.value = err instanceof Error ? err.message : 'Dry-run failed';
  } finally {
    triggering.value = false;
    await loadData();
  }
}

function summarizePatch(round: EvolutionRound): string {
  const entries = round.output_patch?.entries || [];
  if (entries.length === 0) return 'no changes';
  const counts: Record<string, number> = {};
  for (const e of entries) counts[e.op] = (counts[e.op] || 0) + 1;
  const parts: string[] = [];
  if (counts.create) parts.push(`+${counts.create} create`);
  if (counts.supersede) parts.push(`~${counts.supersede} supersede`);
  if (counts.disable) parts.push(`-${counts.disable} disable`);
  return parts.join(', ') || 'no changes';
}

async function approve(round: EvolutionRound) {
  if (actingRoundId.value) return;
  actingRoundId.value = round.id;
  actionError.value = null;
  try {
    const result = await harnessEvolutionApi.approve(round.id);
    if (result.status !== 'applied') {
      actionError.value = result.error || `Approve returned ${result.status}`;
    }
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : 'Approve failed';
  } finally {
    actingRoundId.value = null;
    await loadData();
  }
}

async function abort(round: EvolutionRound) {
  if (actingRoundId.value) return;
  actingRoundId.value = round.id;
  actionError.value = null;
  try {
    const result = await harnessEvolutionApi.abort(round.id, 'operator rejected');
    if (result.status !== 'aborted') {
      actionError.value = result.error || `Abort returned ${result.status}`;
    }
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : 'Abort failed';
  } finally {
    actingRoundId.value = null;
    await loadData();
  }
}

onMounted(loadData);
</script>

<template>
  <section
    id="harness-evolution"
    class="lane-card"
    data-testid="harness-evolution-card"
  >
    <header class="lane-card__head">
      <div>
        <h2 class="lane-card__title">Harness evolution rounds</h2>
        <p class="lane-card__subtitle">
          Codex-proposed patches to the four-layer harness IR. Approve a
          dry-run to apply it; abort to reject.
        </p>
      </div>
    </header>

    <section class="trigger" data-testid="evolution-trigger-section">
      <h3 class="trigger__title">Run a new round</h3>
      <div class="trigger__form">
        <label class="trigger__label">
          Bot
          <select
            v-model="selectedBotId"
            class="trigger__select"
            data-testid="evolution-trigger-bot-select"
            :disabled="triggering"
          >
            <option v-if="bots.length === 0" value="" disabled>
              No bots available
            </option>
            <option v-for="b in bots" :key="b.id" :value="b.id">
              {{ b.name }} ({{ b.id }})
            </option>
          </select>
        </label>
        <button
          class="btn btn-trigger"
          :disabled="!canTrigger"
          data-testid="evolution-trigger-dry-run"
          @click="runDryRun"
        >
          {{ triggering ? 'Running…' : 'Dry-run' }}
        </button>
      </div>
      <p
        v-if="triggerError"
        class="trigger__error"
        role="alert"
        data-testid="evolution-trigger-error"
      >{{ triggerError }}</p>
      <p
        v-else-if="triggerStatus"
        class="trigger__status"
        data-testid="evolution-trigger-status"
      >{{ triggerStatus }}</p>
      <p class="trigger__hint">
        Live runs (auto-apply without approval) require the CLI:
        <code>uv run python scripts/run_harness_evolution.py &lt;bot_id&gt;</code>.
      </p>
    </section>

    <LoadingState v-if="isLoading" message="Loading…" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="loadData" />
    <p v-else-if="isEmpty" class="empty" data-testid="harness-evolution-empty">
      No evolution rounds yet.
    </p>
    <template v-else>
      <p v-if="actionError" class="action-error" role="alert">
        {{ actionError }}
      </p>
      <ul class="rounds">
        <li
          v-for="r in rounds"
          :key="r.id"
          class="round round--clickable"
          :data-testid="`evolution-round-${r.id}`"
          :data-status="r.status"
          @click="openDetail(r)"
        >
          <div class="round__head">
            <span
              class="round__pill"
              :style="{ background: EVOLUTION_STATUS_COLOR_VAR[r.status] }"
            >
              {{ EVOLUTION_STATUS_LABEL[r.status] }}
            </span>
            <code class="round__bot">{{ r.bot_id }}</code>
            <span class="round__when">{{ r.started_at }}</span>
          </div>
          <div class="round__body">
            <span class="round__summary">{{ summarizePatch(r) }}</span>
            <span
              v-if="r.input_execution_count"
              class="round__inputs"
            >· {{ r.input_execution_count }} traj</span>
          </div>
          <p
            v-if="r.notes"
            class="round__notes"
            :data-testid="`evolution-round-notes-${r.id}`"
          >{{ r.notes }}</p>
          <p
            v-if="r.error_message"
            class="round__error"
            :data-testid="`evolution-round-error-${r.id}`"
          >{{ r.error_message }}</p>
          <div
            v-if="r.status === 'awaiting_approval'"
            class="round__actions"
            @click.stop
          >
            <button
              class="btn btn-approve"
              :disabled="actingRoundId === r.id"
              :data-testid="`evolution-approve-${r.id}`"
              @click="approve(r)"
            >
              Approve
            </button>
            <button
              class="btn btn-abort"
              :disabled="actingRoundId === r.id"
              :data-testid="`evolution-abort-${r.id}`"
              @click="abort(r)"
            >
              Abort
            </button>
          </div>
        </li>
      </ul>
    </template>

    <HarnessEvolutionDetailModal
      :round="detailRound"
      @close="closeDetail"
      @approve="approveFromDetail"
      @abort="abortFromDetail"
    />
  </section>
</template>

<style scoped>
.lane-card {
  padding: 20px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 10px;
  background: var(--bg-secondary, rgba(255, 255, 255, 0.02));
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.lane-card__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.lane-card__title { font-size: 14px; font-weight: 600; margin: 0; color: var(--text-primary); }
.lane-card__subtitle { font-size: 12px; margin: 4px 0 0; color: var(--text-tertiary); }

.empty { font-size: 12px; color: var(--text-tertiary); margin: 0; }

.action-error {
  font-size: 12px;
  color: var(--accent-red, #ef4444);
  margin: 0;
}

.rounds { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }

.round {
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
}
.round--clickable { cursor: pointer; transition: border-color 0.15s; }
.round--clickable:hover { border-color: var(--accent-cyan, #06b6d4); }
.round__head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.round__pill { font-size: 10px; font-weight: 700; color: white; padding: 2px 6px; border-radius: 4px; letter-spacing: 0.04em; }
.round__bot { font-family: var(--font-mono, monospace); font-size: 12px; color: var(--text-secondary); }
.round__when { font-size: 11px; color: var(--text-tertiary); margin-left: auto; }

.round__body { display: flex; gap: 6px; font-size: 12px; color: var(--text-secondary); }
.round__summary { font-weight: 500; }
.round__inputs { color: var(--text-tertiary); }

.round__notes,
.round__error {
  font-size: 11px;
  margin: 0;
  color: var(--text-tertiary);
  white-space: pre-wrap;
}
.round__error { color: var(--accent-red, #ef4444); }

.round__actions { display: flex; gap: 8px; margin-top: 4px; }
.btn {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.12));
  background: var(--bg-secondary, transparent);
  color: var(--text-primary);
  cursor: pointer;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-approve { border-color: var(--accent-green, #10b981); color: var(--accent-green, #10b981); }
.btn-abort { border-color: var(--accent-red, #ef4444); color: var(--accent-red, #ef4444); }

.trigger {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
}
.trigger__title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin: 0;
}
.trigger__form { display: flex; gap: 10px; align-items: flex-end; flex-wrap: wrap; }
.trigger__label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--text-tertiary);
  flex: 1;
  min-width: 200px;
}
.trigger__select {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
  color: var(--text-primary);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.12));
  border-radius: 4px;
  padding: 6px 8px;
  font-size: 12px;
  font-family: var(--font-mono, monospace);
}
.btn-trigger {
  border-color: var(--accent-cyan, #06b6d4);
  color: var(--accent-cyan, #06b6d4);
  font-size: 12px;
  padding: 6px 14px;
}
.trigger__error { font-size: 12px; color: var(--accent-red, #ef4444); margin: 0; }
.trigger__status { font-size: 12px; color: var(--text-secondary); margin: 0; }
.trigger__hint { font-size: 11px; color: var(--text-tertiary); margin: 0; }
.trigger__hint code {
  font-family: var(--font-mono, monospace);
  font-size: 10.5px;
  padding: 1px 4px;
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
  border-radius: 3px;
}
</style>
