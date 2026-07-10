<script setup lang="ts">
/**
 * Memory Health — Tesserae 0.17 `doctor`: init / graph-parse / registry /
 * staleness / lock checks for this instance's knowledge graph, grouped by
 * severity. Sibling of ActivitySummaryPage / DecisionsPage.
 */
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { memorySystemApi } from '../services/api/memory-system';
import type { DoctorFinding, DoctorReport } from '../services/api/memory-system';

const { t } = useI18n();

const report = ref<DoctorReport | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const SEV_ORDER: Record<string, number> = { error: 0, warn: 1, ok: 2 };

const findings = computed<DoctorFinding[]>(() =>
  [...(report.value?.findings || [])].sort(
    (a, b) => (SEV_ORDER[a.severity] ?? 3) - (SEV_ORDER[b.severity] ?? 3),
  ),
);

const counts = computed(() => {
  const c: Record<string, number> = { error: 0, warn: 0, ok: 0 };
  for (const f of report.value?.findings || []) c[f.severity] = (c[f.severity] ?? 0) + 1;
  return c;
});

function sevMod(s: string): string {
  if (s === 'error') return 'error';
  if (s === 'warn') return 'warn';
  return 'ok';
}

async function load(refresh = false) {
  loading.value = true;
  error.value = null;
  try {
    const res = await memorySystemApi.doctor(refresh);
    report.value = res.report;
    if (!res.ok) error.value = res.reason || t('memoryDoctor.failed');
  } catch (e) {
    error.value = (e as Error).message || t('memoryDoctor.failed');
  } finally {
    loading.value = false;
  }
}

onMounted(() => load());
</script>

<template>
  <div class="doctor-page">
    <PageHeader :title="t('memoryDoctor.title')" :subtitle="t('memoryDoctor.subtitle')">
      <template #actions>
        <button class="doctor-refresh" :disabled="loading" @click="load(true)">
          {{ t('memoryDoctor.refresh') }}
        </button>
      </template>
    </PageHeader>

    <div v-if="loading" class="doctor-state">{{ t('memoryDoctor.loading') }}</div>
    <div v-else-if="error" class="doctor-state doctor-state--error">{{ error }}</div>

    <template v-else-if="report">
      <div class="doctor-counts">
        <span class="doctor-pill doctor-pill--error">{{ counts.error }} {{ t('memoryDoctor.errors') }}</span>
        <span class="doctor-pill doctor-pill--warn">{{ counts.warn }} {{ t('memoryDoctor.warnings') }}</span>
        <span class="doctor-pill doctor-pill--ok">{{ counts.ok }} {{ t('memoryDoctor.ok') }}</span>
        <span class="doctor-root" :title="report.project_root">{{ report.project_root }}</span>
      </div>

      <ul class="doctor-findings">
        <li
          v-for="f in findings"
          :key="f.check_id"
          class="doctor-finding"
          :class="`doctor-finding--${sevMod(f.severity)}`"
        >
          <div class="doctor-finding__head">
            <span class="doctor-finding__id">{{ f.check_id }}</span>
            <span class="doctor-finding__cat">{{ f.category }}</span>
            <span v-if="f.fixable" class="doctor-finding__fixable">{{ t('memoryDoctor.fixable') }}</span>
          </div>
          <div class="doctor-finding__msg">{{ f.message }}</div>
          <div v-if="f.suggestion" class="doctor-finding__suggestion">{{ f.suggestion }}</div>
        </li>
      </ul>
    </template>

    <div v-else class="doctor-state">{{ t('memoryDoctor.empty') }}</div>
  </div>
</template>

<style scoped>
.doctor-page {
  padding: 24px;
  max-width: 920px;
}
.doctor-refresh {
  padding: 6px 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary, #e4e4e7);
  font-size: 13px;
  cursor: pointer;
}
.doctor-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.doctor-state {
  padding: 40px;
  text-align: center;
  color: var(--text-secondary, #a1a1aa);
}
.doctor-state--error {
  color: #ef4444;
}
.doctor-counts {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 16px 0 20px;
}
.doctor-pill {
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 100px;
}
.doctor-pill--error {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
}
.doctor-pill--warn {
  background: rgba(234, 179, 8, 0.15);
  color: #eab308;
}
.doctor-pill--ok {
  background: rgba(34, 197, 94, 0.12);
  color: #4ade80;
}
.doctor-root {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-secondary, #71717a);
  max-width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doctor-findings {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.doctor-finding {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-left-width: 3px;
  border-radius: 10px;
  padding: 12px 14px;
}
.doctor-finding--error {
  border-left-color: #ef4444;
}
.doctor-finding--warn {
  border-left-color: #eab308;
}
.doctor-finding--ok {
  border-left-color: #22c55e;
}
.doctor-finding__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.doctor-finding__id {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #e4e4e7);
}
.doctor-finding__cat {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-secondary, #71717a);
}
.doctor-finding__fixable {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 100px;
  background: rgba(79, 70, 229, 0.15);
  color: #a5b4fc;
}
.doctor-finding__msg {
  font-size: 13px;
  color: var(--text-primary, #d4d4d8);
  margin-top: 4px;
}
.doctor-finding__suggestion {
  font-size: 12px;
  color: var(--text-secondary, #a1a1aa);
  margin-top: 4px;
}
</style>
