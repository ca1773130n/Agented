<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ResearchThread } from '../../../services/api/research';

const props = defineProps<{
  threads: ResearchThread[];
}>();

const { t } = useI18n();

const total = computed(() => props.threads.length);
const completed = computed(
  () => props.threads.filter((th) => th.status === 'complete' || th.status === 'completed').length,
);
const running = computed(() => props.threads.filter((th) => th.status === 'running').length);
const totalIterations = computed(() => props.threads.reduce((acc, th) => acc + (th.iteration || 0), 0));
</script>

<template>
  <section class="portfolio-runs">
    <h3 class="pr-title">{{ t('surface.research.portfolio.title') }}</h3>
    <div class="pr-grid">
      <div class="pr-stat">
        <span class="pr-value">{{ total }}</span>
        <span class="pr-label">{{ t('surface.research.portfolio.total') }}</span>
      </div>
      <div class="pr-stat">
        <span class="pr-value">{{ running }}</span>
        <span class="pr-label">{{ t('surface.research.portfolio.running') }}</span>
      </div>
      <div class="pr-stat">
        <span class="pr-value">{{ completed }}</span>
        <span class="pr-label">{{ t('surface.research.portfolio.completed') }}</span>
      </div>
      <div class="pr-stat">
        <span class="pr-value">{{ totalIterations }}</span>
        <span class="pr-label">{{ t('surface.research.portfolio.iterations') }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.portfolio-runs {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pr-title {
  font-size: 0.95rem;
  margin: 0;
}
.pr-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.pr-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  text-align: center;
}
.pr-value {
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--text-primary);
}
.pr-label {
  font-size: 0.7rem;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
</style>
