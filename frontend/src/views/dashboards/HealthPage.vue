<!--
  HealthPage — Health lane.
  Composes HealthMonitor + BotHealth + ServiceHealth + BotEffectiveness.
-->
<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import PageHeader from '../../components/base/PageHeader.vue';
import HealthMonitorCard from './cards/HealthMonitorCard.vue';
import BotHealthCard from './cards/BotHealthCard.vue';
import ServiceHealthCard from './cards/ServiceHealthCard.vue';
import BotEffectivenessCard from './cards/BotEffectivenessCard.vue';

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
  <div class="lane-page health-lane">
    <PageHeader title="Health" subtitle="System, per-bot, per-service, and per-bot effectiveness rollups" />
    <div class="lane-cards">
      <HealthMonitorCard @loaded="onCardLoaded" />
      <BotHealthCard @loaded="onCardLoaded" />
      <ServiceHealthCard @loaded="onCardLoaded" />
      <BotEffectivenessCard @loaded="onCardLoaded" />
    </div>
  </div>
</template>

<style scoped>
.lane-page { display: flex; flex-direction: column; gap: 24px; width: 100%; }
.lane-cards { display: flex; flex-direction: column; gap: 24px; }
</style>
