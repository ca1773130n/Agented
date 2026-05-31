<!--
  QualityPage — multi-card lane for Quality dashboards.
  Composes SecurityCard + PrReviewCard + AnomalyDetectionCard.
  Anchor-scrolls to route.hash slug after the matching card emits `loaded`.
-->
<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import PageHeader from '../../components/base/PageHeader.vue';
import SecurityCard from './cards/SecurityCard.vue';
import PrReviewCard from './cards/PrReviewCard.vue';
import AnomalyDetectionCard from './cards/AnomalyDetectionCard.vue';

const { t } = useI18n();
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
  <div class="lane-page quality-lane">
    <PageHeader :title="t('quality.title')" :subtitle="t('quality.subtitle')" />
    <div class="lane-cards">
      <SecurityCard @loaded="onCardLoaded" />
      <PrReviewCard @loaded="onCardLoaded" />
      <AnomalyDetectionCard @loaded="onCardLoaded" />
    </div>
  </div>
</template>

<style scoped>
.lane-page { display: flex; flex-direction: column; gap: 24px; width: 100%; }
.lane-cards { display: flex; flex-direction: column; gap: 24px; }
</style>
