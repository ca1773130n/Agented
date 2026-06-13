<script setup lang="ts">
/**
 * RoundList (REQ-16) — lists evolution rounds, either project-scoped
 * (listProjectRounds) or globally (listAllRounds when no projectId is given).
 * Emits `select` with a round id for RoundDetail to load.
 */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../services/api';
import type { HarnessRound } from '../../../services/api/grdHarness';

const props = defineProps<{ projectId?: string }>();
const emit = defineEmits<{ (e: 'select', roundId: string): void }>();

const { t } = useI18n();
const rounds = ref<HarnessRound[]>([]);
const isLoading = ref(true);
const selectedId = ref<string | null>(null);

async function load() {
  try {
    isLoading.value = true;
    if (props.projectId) {
      const res = await grdHarnessApi.listProjectRounds(props.projectId);
      rounds.value = res.rounds || [];
    } else {
      const res = await grdHarnessApi.listAllRounds();
      rounds.value = res.rounds || [];
    }
  } catch {
    rounds.value = [];
  } finally {
    isLoading.value = false;
  }
}

function select(id: string) {
  selectedId.value = id;
  emit('select', id);
}

onMounted(load);
defineExpose({ load });
</script>

<template>
  <div class="round-list card">
    <div class="card-header"><h3>{{ t('surface.harness.rounds.title') }}</h3></div>
    <div class="card-body">
      <span v-if="isLoading" class="muted">{{ t('surface.harness.rounds.loading') }}</span>
      <span v-else-if="rounds.length === 0" class="muted">{{ t('surface.harness.rounds.empty') }}</span>
      <ul v-else class="rows">
        <li
          v-for="r in rounds"
          :key="r.round_id"
          :class="['row', { active: selectedId === r.round_id }]"
          @click="select(r.round_id)"
        >
          <span class="rid">{{ r.round_id }}</span>
          <span class="status">{{ r.status || t('surface.harness.rounds.unknownStatus') }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.round-list { border: 1px solid var(--border-default); border-radius: 8px; }
.card-header { padding: 1rem 1.25rem; border-bottom: 1px solid var(--border-default); }
.card-header h3 { margin: 0; font-size: 0.95rem; color: var(--text-primary, #fff); }
.card-body { padding: 1rem 1.25rem; }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.row { display: flex; justify-content: space-between; padding: 0.5rem 0.75rem; border-radius: 6px; cursor: pointer; }
.row:hover, .row.active { background: var(--bg-tertiary, #1a1a24); }
.rid { color: var(--text-primary, #fff); font-size: 0.85rem; font-family: monospace; }
.status { color: var(--text-tertiary, #888); font-size: 0.8rem; }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
