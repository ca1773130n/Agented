<script setup lang="ts">
/**
 * RoundDetail (REQ-16) — loads a round's detail + impact and exposes
 * approve / abort / revert actions.
 *
 * CRITICAL (plan must-have): revert is destructive (git-reversible) and MUST be
 * confirm-guarded. Clicking "Revert" does NOT call the API — it opens a
 * confirmation step; only the explicit "Confirm revert" action calls
 * grdHarnessApi.revertRound. This two-step guard is asserted by the test.
 */
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../services/api';
import { ApiError } from '../../../services/api';
import type { HarnessRound } from '../../../services/api/grdHarness';
import { useToast } from '../../../composables/useToast';

const props = defineProps<{ roundId: string | null }>();
const emit = defineEmits<{ (e: 'changed'): void }>();

const { t } = useI18n();
const showToast = useToast();

const detail = ref<HarnessRound | null>(null);
const impact = ref<Record<string, unknown> | null>(null);
const isLoading = ref(false);
const busy = ref(false);
const confirmingRevert = ref(false);

async function load(id: string) {
  try {
    isLoading.value = true;
    confirmingRevert.value = false;
    const [d, i] = await Promise.all([
      grdHarnessApi.getRoundDetail(id),
      grdHarnessApi.getRoundImpact(id),
    ]);
    detail.value = d;
    impact.value = i;
  } catch {
    detail.value = null;
    impact.value = null;
  } finally {
    isLoading.value = false;
  }
}

async function approve() {
  if (!props.roundId) return;
  await run(() => grdHarnessApi.approveRound(props.roundId as string), 'approved');
}

async function abort() {
  if (!props.roundId) return;
  await run(() => grdHarnessApi.abortRound(props.roundId as string), 'aborted');
}

// Step 1 of the revert guard: arm the confirmation. NO API call here.
function requestRevert() {
  confirmingRevert.value = true;
}

function cancelRevert() {
  confirmingRevert.value = false;
}

// Step 2 of the revert guard: only this explicit action hits the API.
async function confirmRevert() {
  if (!props.roundId) return;
  await run(() => grdHarnessApi.revertRound(props.roundId as string), 'reverted');
  confirmingRevert.value = false;
}

async function run(fn: () => Promise<unknown>, key: 'approved' | 'aborted' | 'reverted') {
  try {
    busy.value = true;
    await fn();
    showToast(t(`surface.harness.rounds.${key}`), 'success');
    emit('changed');
    if (props.roundId) await load(props.roundId);
  } catch (e) {
    const message = e instanceof ApiError ? e.message : t('surface.harness.rounds.actionFailed');
    showToast(message, 'error');
  } finally {
    busy.value = false;
  }
}

watch(
  () => props.roundId,
  (id) => {
    if (id) load(id);
    else {
      detail.value = null;
      impact.value = null;
    }
  },
  { immediate: true },
);
</script>

<template>
  <div class="round-detail card">
    <div class="card-header"><h3>{{ t('surface.harness.rounds.detailTitle') }}</h3></div>
    <div class="card-body">
      <span v-if="!roundId" class="muted">{{ t('surface.harness.rounds.selectPrompt') }}</span>
      <span v-else-if="isLoading" class="muted">{{ t('surface.harness.rounds.loading') }}</span>
      <template v-else-if="detail">
        <div class="meta">
          <div><span class="lbl">{{ t('surface.harness.rounds.idLabel') }}</span> {{ detail.round_id }}</div>
          <div><span class="lbl">{{ t('surface.harness.rounds.statusLabel') }}</span> {{ detail.status }}</div>
        </div>
        <pre v-if="impact" class="impact">{{ JSON.stringify(impact, null, 2) }}</pre>

        <div class="actions">
          <button class="btn" :disabled="busy" @click="approve">
            {{ t('surface.harness.rounds.approve') }}
          </button>
          <button class="btn" :disabled="busy" @click="abort">
            {{ t('surface.harness.rounds.abort') }}
          </button>
          <button
            v-if="!confirmingRevert"
            class="btn btn-danger"
            :disabled="busy"
            @click="requestRevert"
          >
            {{ t('surface.harness.rounds.revert') }}
          </button>
        </div>

        <div v-if="confirmingRevert" class="revert-confirm">
          <p class="warn">{{ t('surface.harness.rounds.revertWarning') }}</p>
          <div class="actions">
            <button class="btn" :disabled="busy" @click="cancelRevert">
              {{ t('surface.harness.rounds.revertCancel') }}
            </button>
            <button class="btn btn-danger" :disabled="busy" @click="confirmRevert">
              {{ t('surface.harness.rounds.revertConfirm') }}
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.round-detail { border: 1px solid var(--border-default); border-radius: 8px; }
.card-header { padding: 1rem 1.25rem; border-bottom: 1px solid var(--border-default); }
.card-header h3 { margin: 0; font-size: 0.95rem; color: var(--text-primary, #fff); }
.card-body { padding: 1.25rem; display: flex; flex-direction: column; gap: 1rem; }
.meta { display: flex; flex-direction: column; gap: 4px; font-size: 0.85rem; color: var(--text-secondary, #aaa); }
.lbl { color: var(--text-tertiary, #888); }
.impact { background: var(--bg-tertiary, #1a1a24); border-radius: 6px; padding: 0.75rem; font-size: 0.75rem; max-height: 220px; overflow: auto; color: var(--text-secondary, #aaa); }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.btn-danger { color: #ff6b6b; border-color: #ff6b6b; }
.revert-confirm { border: 1px solid #ff6b6b; border-radius: 6px; padding: 0.75rem; }
.warn { color: #ff6b6b; font-size: 0.85rem; margin: 0 0 0.5rem; }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
