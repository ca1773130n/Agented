<script setup lang="ts">
/**
 * ConversionAudit — the Loop-4 Tier-1 effectiveness readout. Wraps GRD 0.4.16
 * `gd harness conversion`: a DETERMINISTIC audit (no LLM, no re-run) of whether
 * recorded life-harness lessons actually converted into file/gate/prompt changes,
 * and whether recurring failures stopped. Cheapest of the three replay tiers —
 * grades real conversion outcomes, not the agent's self-narration.
 *
 * 503 (gd binary missing / <0.4.16) is expected on projects without the GRD
 * life-harness — degrade to a muted "unavailable" note, never an error banner.
 */
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../services/api';
import type { HarnessConversionResult } from '../../../services/api/grdHarness';

const props = defineProps<{ projectId: string }>();
const { t } = useI18n();

const data = ref<HarnessConversionResult | null>(null);
const isLoading = ref(true);
const unavailable = ref(false);

async function load() {
  try {
    isLoading.value = true;
    unavailable.value = false;
    data.value = await grdHarnessApi.harnessConversion(props.projectId);
  } catch {
    // 503 or any transport error → the audit simply isn't available here.
    data.value = null;
    unavailable.value = true;
  } finally {
    isLoading.value = false;
  }
}

const ratePct = computed(() => {
  const r = data.value?.conversion_rate;
  return typeof r === 'number' ? `${Math.round(r * 100)}%` : '—';
});
const recurring = computed(() => data.value?.harness_policy?.recurring_count ?? 0);
const topUnconverted = computed(() => (data.value?.top_unconverted ?? []).slice(0, 5));

function label(entry: Record<string, unknown>): string {
  return String(entry.lesson ?? entry.title ?? entry.summary ?? entry.id ?? JSON.stringify(entry));
}

onMounted(load);
defineExpose({ load });
</script>

<template>
  <div class="conversion-audit card">
    <div class="card-header">
      <h3>{{ t('surface.harness.conversion.title') }}</h3>
      <span class="hint">{{ t('surface.harness.conversion.hint') }}</span>
    </div>
    <div class="card-body">
      <span v-if="isLoading" class="muted">{{ t('surface.harness.conversion.loading') }}</span>
      <span v-else-if="unavailable" class="muted">{{ t('surface.harness.conversion.unavailable') }}</span>
      <template v-else-if="data">
        <div class="metrics">
          <div class="metric">
            <span class="value">{{ ratePct }}</span>
            <span class="label">{{ t('surface.harness.conversion.rate') }}</span>
          </div>
          <div class="metric">
            <span class="value">{{ data.lessons_converted ?? 0 }} / {{ data.lessons_total ?? 0 }}</span>
            <span class="label">{{ t('surface.harness.conversion.lessons') }}</span>
          </div>
          <div class="metric">
            <span class="value">{{ data.median_latency_rounds ?? '—' }}</span>
            <span class="label">{{ t('surface.harness.conversion.latency') }}</span>
          </div>
          <div class="metric" :class="{ warn: recurring > 0 }">
            <span class="value">{{ recurring }}</span>
            <span class="label">{{ t('surface.harness.conversion.recurring') }}</span>
          </div>
        </div>
        <div v-if="topUnconverted.length" class="unconverted">
          <span class="sub">{{ t('surface.harness.conversion.topUnconverted') }}</span>
          <ul>
            <li v-for="(entry, i) in topUnconverted" :key="i">{{ label(entry) }}</li>
          </ul>
        </div>
        <span v-else class="muted small">{{ t('surface.harness.conversion.allConverted') }}</span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.conversion-audit { border: 1px solid var(--border-default); border-radius: 8px; }
.card-header { padding: 1rem 1.25rem; border-bottom: 1px solid var(--border-default); display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
.card-header h3 { margin: 0; font-size: 0.95rem; color: var(--text-primary, #fff); }
.hint { color: var(--text-tertiary, #888); font-size: 0.75rem; }
.card-body { padding: 1rem 1.25rem; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.metric { display: flex; flex-direction: column; gap: 2px; padding: 0.75rem; background: var(--bg-tertiary, #1a1a24); border-radius: 6px; }
.metric .value { font-size: 1.25rem; font-weight: 600; color: var(--text-primary, #fff); font-family: monospace; }
.metric .label { font-size: 0.72rem; color: var(--text-tertiary, #888); }
.metric.warn .value { color: var(--color-warning, #e0a030); }
.unconverted { margin-top: 1rem; }
.unconverted .sub { font-size: 0.78rem; color: var(--text-secondary, #aaa); }
.unconverted ul { margin: 0.4rem 0 0; padding-left: 1.1rem; }
.unconverted li { font-size: 0.82rem; color: var(--text-secondary, #aaa); margin-bottom: 2px; }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
.muted.small { font-size: 0.8rem; }
@media (max-width: 720px) {
  .metrics { grid-template-columns: repeat(2, 1fr); }
}
</style>
