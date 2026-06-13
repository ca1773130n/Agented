<script setup lang="ts">
/** DeadEndsPanel — routes 3,4,5: addDeadEnd, promoteDeadEnds, listDeadEnds. */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../../services/api';
import type { DeadEndEntry } from '../../../../services/api/grdHarness';

const props = defineProps<{ projectId: string }>();
const { t } = useI18n();

const items = ref<DeadEndEntry[]>([]);
const loading = ref(false);
const approach = ref('');
const reason = ref('');
const phase = ref('');
const promotePhase = ref('');

async function load() {
  try {
    loading.value = true;
    const res = await grdHarnessApi.listDeadEnds(props.projectId);
    items.value = res.dead_ends || [];
  } catch {
    items.value = [];
  } finally {
    loading.value = false;
  }
}

async function add() {
  if (!approach.value || !reason.value) return;
  await grdHarnessApi.addDeadEnd(props.projectId, {
    approach: approach.value,
    reason: reason.value,
    phase: phase.value || null,
  });
  approach.value = '';
  reason.value = '';
  phase.value = '';
  await load();
}

async function promote() {
  if (!promotePhase.value) return;
  await grdHarnessApi.promoteDeadEnds(props.projectId, promotePhase.value);
  await load();
}

onMounted(load);
</script>

<template>
  <div class="panel">
    <h4>{{ t('surface.harness.panels.deadEnds.title') }}</h4>
    <ul v-if="items.length" class="rows">
      <li v-for="(d, i) in items" :key="i" class="row">
        <strong>{{ d.approach }}</strong>
        <span class="muted">{{ d.reason }}</span>
      </li>
    </ul>
    <span v-else class="muted">{{ t('surface.harness.panels.deadEnds.empty') }}</span>

    <div class="form">
      <input v-model="approach" :placeholder="t('surface.harness.panels.deadEnds.approach')" />
      <input v-model="reason" :placeholder="t('surface.harness.panels.deadEnds.reason')" />
      <input v-model="phase" :placeholder="t('surface.harness.panels.deadEnds.phase')" />
      <button class="btn" @click="add">{{ t('surface.harness.panels.deadEnds.add') }}</button>
    </div>
    <div class="form">
      <input
        v-model="promotePhase"
        :placeholder="t('surface.harness.panels.deadEnds.promotePlaceholder')"
      />
      <button class="btn" @click="promote">
        {{ t('surface.harness.panels.deadEnds.promote') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 0.75rem; }
h4 { margin: 0; font-size: 0.9rem; color: var(--text-primary, #fff); }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.row { display: flex; flex-direction: column; padding: 0.5rem; background: var(--bg-tertiary, #1a1a24); border-radius: 6px; }
.row strong { color: var(--text-primary, #fff); font-size: 0.85rem; }
.form { display: flex; gap: 6px; flex-wrap: wrap; }
.form input { flex: 1; min-width: 120px; padding: 0.5rem; background: var(--bg-tertiary, #1a1a24); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-primary, #fff); }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
