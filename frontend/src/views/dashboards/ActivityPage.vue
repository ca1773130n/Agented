<!--
  ActivityPage — Activity lane.

  Sub-grouped per audit into three visual blocks:
    - Live ops:        Scheduling, Execution Queue, Execution Volume, Success Rate
    - Reports:         Impact Report, Cross-Team Insights, ROI Leaderboard
    - Inspector tools: deep-links to per-execution inspectors (timeline, diff,
                       artifacts, cost, time-travel) + the traces explorer.
-->
<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import PageHeader from '../../components/base/PageHeader.vue';
import SchedulingCard from './cards/SchedulingCard.vue';
import ExecutionQueueCard from './cards/ExecutionQueueCard.vue';
import ExecutionVolumeCard from './cards/ExecutionVolumeCard.vue';
import SuccessRateCard from './cards/SuccessRateCard.vue';
import HarnessLayerCard from './cards/HarnessLayerCard.vue';
import HarnessEvolutionCard from './cards/HarnessEvolutionCard.vue';
import HarnessTakeawaysCard from './cards/HarnessTakeawaysCard.vue';
import ImpactReportCard from './cards/ImpactReportCard.vue';
import CrossTeamInsightsCard from './cards/CrossTeamInsightsCard.vue';
import RoiLeaderboardCard from './cards/RoiLeaderboardCard.vue';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const loaded = ref<Set<string>>(new Set());

interface InspectorTool {
  label: string;
  routeName: string;
  description: string;
}

const inspectorTools: InspectorTool[] = [
  {
    label: t('activity.inspector.timeline.label'),
    routeName: 'execution-timeline',
    description: t('activity.inspector.timeline.description'),
  },
  {
    label: t('activity.inspector.artifacts.label'),
    routeName: 'execution-artifacts',
    description: t('activity.inspector.artifacts.description'),
  },
  {
    label: t('activity.inspector.diffViewer.label'),
    routeName: 'execution-file-diff-viewer',
    description: t('activity.inspector.diffViewer.description'),
  },
  {
    label: t('activity.inspector.timeTravel.label'),
    routeName: 'execution-time-travel-debugger',
    description: t('activity.inspector.timeTravel.description'),
  },
  {
    label: t('activity.inspector.costEstimator.label'),
    routeName: 'execution-cost-estimator',
    description: t('activity.inspector.costEstimator.description'),
  },
  {
    label: t('activity.inspector.traces.label'),
    routeName: 'traces-list',
    description: t('activity.inspector.traces.description'),
  },
];

function onCardLoaded(slug: string) {
  loaded.value.add(slug);
  maybeScroll();
}

function maybeScroll() {
  const hash = (route.hash || '').replace(/^#/, '');
  if (!hash) return;
  if (!loaded.value.has(hash)) return;
  nextTick(() => {
    const el = document.getElementById(hash);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function openInspector(tool: InspectorTool) {
  router.push({ name: tool.routeName });
}

onMounted(maybeScroll);
</script>

<template>
  <div class="lane-page activity-lane">
    <PageHeader :title="t('activity.title')" :subtitle="t('activity.subtitle')" />

    <section class="lane-block" :aria-label="t('activity.blocks.liveOps')">
      <h2 class="lane-block__title">{{ t('activity.blocks.liveOps') }}</h2>
      <div class="lane-cards">
        <SchedulingCard @loaded="onCardLoaded" />
        <ExecutionQueueCard @loaded="onCardLoaded" />
        <ExecutionVolumeCard @loaded="onCardLoaded" />
        <SuccessRateCard @loaded="onCardLoaded" />
        <HarnessLayerCard @loaded="onCardLoaded" />
        <HarnessTakeawaysCard @loaded="onCardLoaded" />
        <HarnessEvolutionCard @loaded="onCardLoaded" />
      </div>
    </section>

    <section class="lane-block" :aria-label="t('activity.blocks.reports')">
      <h2 class="lane-block__title">{{ t('activity.blocks.reports') }}</h2>
      <div class="lane-cards">
        <ImpactReportCard @loaded="onCardLoaded" />
        <CrossTeamInsightsCard @loaded="onCardLoaded" />
        <RoiLeaderboardCard @loaded="onCardLoaded" />
      </div>
    </section>

    <section class="lane-block" :aria-label="t('activity.blocks.inspectorTools')">
      <h2 class="lane-block__title">{{ t('activity.blocks.inspectorTools') }}</h2>
      <div class="inspector-grid">
        <button
          v-for="tool in inspectorTools"
          :key="tool.routeName"
          class="inspector-tile"
          :data-testid="`inspector-tile-${tool.routeName}`"
          @click="openInspector(tool)"
        >
          <span class="inspector-tile__label">{{ tool.label }}</span>
          <span class="inspector-tile__desc">{{ tool.description }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.lane-page { display: flex; flex-direction: column; gap: 32px; width: 100%; }
.lane-block { display: flex; flex-direction: column; gap: 16px; }
.lane-block__title { font-size: 14px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.06em; margin: 0; }
.lane-cards { display: flex; flex-direction: column; gap: 24px; }

.inspector-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.inspector-tile {
  display: flex; flex-direction: column; gap: 4px;
  padding: 14px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  text-align: left;
  cursor: pointer;
  color: var(--text-primary);
  transition: border-color 0.15s;
}
.inspector-tile:hover { border-color: var(--accent-cyan); }
.inspector-tile__label { font-size: 13px; font-weight: 600; }
.inspector-tile__desc { font-size: 11px; color: var(--text-tertiary); line-height: 1.4; }
</style>
