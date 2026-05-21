<!--
  ActivityPage — Activity lane.

  Sub-grouped per audit into two visual blocks:
    - Live ops: Scheduling, Execution Queue, Execution Volume, Success Rate
    - Reports:  Impact Report, Cross-Team Insights, ROI Leaderboard
-->
<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import PageHeader from '../../components/base/PageHeader.vue';
import SchedulingCard from './cards/SchedulingCard.vue';
import ExecutionQueueCard from './cards/ExecutionQueueCard.vue';
import ExecutionVolumeCard from './cards/ExecutionVolumeCard.vue';
import SuccessRateCard from './cards/SuccessRateCard.vue';
import ImpactReportCard from './cards/ImpactReportCard.vue';
import CrossTeamInsightsCard from './cards/CrossTeamInsightsCard.vue';
import RoiLeaderboardCard from './cards/RoiLeaderboardCard.vue';

const route = useRoute();
const loaded = ref<Set<string>>(new Set());

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

onMounted(maybeScroll);
</script>

<template>
  <div class="lane-page activity-lane">
    <PageHeader title="Activity" subtitle="Live ops + team / org reports" />

    <section class="lane-block" aria-label="Live ops">
      <h2 class="lane-block__title">Live ops</h2>
      <div class="lane-cards">
        <SchedulingCard @loaded="onCardLoaded" />
        <ExecutionQueueCard @loaded="onCardLoaded" />
        <ExecutionVolumeCard @loaded="onCardLoaded" />
        <SuccessRateCard @loaded="onCardLoaded" />
      </div>
    </section>

    <section class="lane-block" aria-label="Reports">
      <h2 class="lane-block__title">Reports</h2>
      <div class="lane-cards">
        <ImpactReportCard @loaded="onCardLoaded" />
        <CrossTeamInsightsCard @loaded="onCardLoaded" />
        <RoiLeaderboardCard @loaded="onCardLoaded" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.lane-page { display: flex; flex-direction: column; gap: 32px; width: 100%; }
.lane-block { display: flex; flex-direction: column; gap: 16px; }
.lane-block__title { font-size: 14px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.06em; margin: 0; }
.lane-cards { display: flex; flex-direction: column; gap: 24px; }
</style>
