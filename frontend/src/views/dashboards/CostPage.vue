<!--
  CostPage — Cost lane. TokenUsageCard owns its own embedded Cost Trend
  chart (see plan §"Cost Trend NOT extracted from Analytics") so this
  page is a single-card lane.
-->
<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import PageHeader from '../../components/base/PageHeader.vue';
import TokenUsageCard from './cards/TokenUsageCard.vue';

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
  <div class="lane-page cost-lane">
    <PageHeader title="Cost" subtitle="Token spend, budgets, and rate-limit windows" />
    <div class="lane-cards">
      <TokenUsageCard @loaded="onCardLoaded" />
    </div>
  </div>
</template>

<style scoped>
.lane-page { display: flex; flex-direction: column; gap: 24px; width: 100%; }
.lane-cards { display: flex; flex-direction: column; gap: 24px; }
</style>
