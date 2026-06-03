<!--
  CostPage — Cost lane. TokenUsageCard owns its own embedded Cost Trend
  chart (see plan §"Cost Trend NOT extracted from Analytics") so this
  page is a single-card lane.
-->
<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import PageHeader from '../../components/base/PageHeader.vue';
import TokenUsageCard from './cards/TokenUsageCard.vue';
import AiCostDashboard from '../AiCostDashboard.vue';

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
  <div class="lane-page cost-lane">
    <PageHeader :title="t('cost.title')" :subtitle="t('cost.subtitle')" />
    <div class="notional-note">
      <span class="notional-icon">ⓘ</span>
      <span>{{ t('cost.billingNote') }}</span>
    </div>
    <div class="lane-cards">
      <TokenUsageCard @loaded="onCardLoaded" />
      <!-- P2: the AI Cost dashboard is folded into the Cost lane (one cost surface). -->
      <section id="ai-cost" class="ai-cost-section">
        <AiCostDashboard />
      </section>
    </div>
  </div>
</template>

<style scoped>
.lane-page { display: flex; flex-direction: column; gap: 24px; width: 100%; }
.lane-cards { display: flex; flex-direction: column; gap: 24px; }
.notional-note {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 12px 16px; margin-top: -8px;
  background: var(--bg-secondary, rgba(255, 255, 255, 0.02));
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
  border-left: 3px solid var(--accent-violet, #a78bfa);
  border-radius: 8px; font-size: 0.8rem; line-height: 1.45;
  color: var(--text-tertiary, #888);
}
.notional-icon { color: var(--accent-violet, #a78bfa); flex-shrink: 0; font-size: 0.95rem; }
</style>
