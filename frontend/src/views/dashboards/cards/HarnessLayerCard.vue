<!--
  HarnessLayerCard — Activity-lane card surfacing Life-Harness annotations.

  Renders four colour-coded badges (H2 / H3 / H4 / General) with the count
  of recently annotated executions whose primary interface failure landed
  in that layer. Reads ``/admin/executions/annotations/summary``.

  Reference: arXiv 2605.22166 (Life-Harness, Appendix A.1).
-->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  HARNESS_LAYER_COLOR_VAR,
  HARNESS_LAYER_LABEL,
  harnessAnnotationsApi,
  type HarnessLayer,
  type HarnessSummaryResponse,
} from '../../../services/api/harness-annotations';
import LoadingState from '../../../components/base/LoadingState.vue';
import ErrorState from '../../../components/base/ErrorState.vue';

const emit = defineEmits<{ loaded: [slug: string] }>();
const { t } = useI18n();

const isLoading = ref(false);
const loadError = ref<string | null>(null);
const summary = ref<HarnessSummaryResponse | null>(null);

const layers: HarnessLayer[] = ['h2', 'h3', 'h4', 'general'];

const total = computed(() => summary.value?.by_layer.total ?? 0);
const noneCount = computed(() => summary.value?.by_layer.none ?? 0);
const isEmpty = computed(() => total.value === 0);

async function loadData() {
  isLoading.value = true;
  loadError.value = null;
  try {
    summary.value = await harnessAnnotationsApi.getSummary({ limit: 5 });
  } catch (err) {
    loadError.value =
      err instanceof Error ? err.message : t('harnessLayerCard.error.load');
  } finally {
    isLoading.value = false;
    emit('loaded', 'harness-layers');
  }
}

onMounted(loadData);
</script>

<template>
  <section id="harness-layers" class="lane-card" data-testid="harness-layer-card">
    <header class="lane-card__head">
      <div>
        <h2 class="lane-card__title">{{ t('harnessLayerCard.title') }}</h2>
        <p class="lane-card__subtitle">
          {{ t('harnessLayerCard.subtitle') }}
        </p>
      </div>
    </header>

    <LoadingState v-if="isLoading" :message="t('harnessLayerCard.loading')" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="loadData" />
    <p v-else-if="isEmpty" class="empty" data-testid="harness-layer-empty">
      {{ t('harnessLayerCard.empty') }}
    </p>
    <template v-else>
      <div class="badges">
        <div
          v-for="layer in layers"
          :key="layer"
          class="badge"
          :data-testid="`harness-layer-badge-${layer}`"
          :style="{ '--badge-color': HARNESS_LAYER_COLOR_VAR[layer] }"
        >
          <span class="badge__dot" />
          <span class="badge__count">
            {{ summary?.by_layer[layer] ?? 0 }}
          </span>
          <span class="badge__label">{{ HARNESS_LAYER_LABEL[layer] }}</span>
        </div>
      </div>
      <p class="meta">
        {{ t('harnessLayerCard.executionsAnnotated', { count: total }) }}
        <span v-if="noneCount">· {{ t('harnessLayerCard.clean', { count: noneCount }) }}</span>
      </p>

      <div
        v-if="summary && summary.recent_failures.length"
        class="recent"
        data-testid="harness-layer-recent"
      >
        <h3 class="recent__title">{{ t('harnessLayerCard.recentFailures') }}</h3>
        <ul class="recent__list">
          <li
            v-for="row in summary.recent_failures"
            :key="row.session_id"
            class="recent__row"
          >
            <span
              class="recent__pill"
              :style="{ background: HARNESS_LAYER_COLOR_VAR[row.primary_layer] }"
            >
              {{ row.primary_layer.toUpperCase() }}
            </span>
            <code class="recent__id">{{ row.session_id }}</code>
            <span class="recent__count">
              {{ t('harnessLayerCard.incidents', { count: row.incident_count }) }}
            </span>
          </li>
        </ul>
      </div>
    </template>
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

.badges {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}
.badge {
  display: flex; flex-direction: column; gap: 4px;
  padding: 12px 14px;
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-left: 3px solid var(--badge-color);
  border-radius: 8px;
}
.badge__dot {
  display: none;  /* reserved for a future "live" indicator */
}
.badge__count { font-size: 22px; font-weight: 600; color: var(--text-primary); }
.badge__label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }

.meta { margin: 0; font-size: 12px; color: var(--text-tertiary); }

.recent { display: flex; flex-direction: column; gap: 8px; }
.recent__title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-tertiary); margin: 0; }
.recent__list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.recent__row { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-secondary); }
.recent__pill { font-size: 10px; font-weight: 700; color: white; padding: 2px 6px; border-radius: 4px; }
.recent__id { font-family: var(--font-mono, monospace); }
.recent__count { color: var(--text-tertiary); }

.empty { font-size: 12px; color: var(--text-tertiary); margin: 0; }
</style>
