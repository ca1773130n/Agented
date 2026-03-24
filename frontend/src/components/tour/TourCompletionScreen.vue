<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { RouterLink } from 'vue-router';
import { TOUR_STEP_DEFINITIONS } from '../../constants/tourSteps';

const props = defineProps<{
  completedSteps: string[]
}>();

const emit = defineEmits<{ done: [] }>();

const { t } = useI18n();

function stepToDisplay(def: typeof TOUR_STEP_DEFINITIONS[number]) {
  const link = def.routeHash ? `${def.route}${def.routeHash}` : def.route;
  return { label: def.label, link };
}

const configuredItems = computed(() =>
  TOUR_STEP_DEFINITIONS
    .filter(d => props.completedSteps.includes(d.key))
    .map(stepToDisplay)
);

const skippedItems = computed(() =>
  TOUR_STEP_DEFINITIONS
    .filter(d => !props.completedSteps.includes(d.key))
    .map(stepToDisplay)
);
</script>

<template>
  <div class="completion-overlay">
    <div class="completion-card">
      <!-- Animated checkmark -->
      <div class="completion-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 12l5 5L19 7" />
        </svg>
      </div>

      <h2 class="completion-heading">{{ t('tour.setupComplete') }}</h2>
      <p class="completion-subtext">{{ t('tour.setupCompleteDesc') }}</p>

      <!-- Configured items -->
      <div v-if="configuredItems.length > 0" class="completion-section">
        <ul class="completion-list">
          <li v-for="item in configuredItems" :key="item.label" class="completion-list-item configured">
            <span class="list-icon configured-icon">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 8l3.5 3.5L13 5" />
              </svg>
            </span>
            <span class="list-label">{{ item.label }}</span>
          </li>
        </ul>
      </div>

      <!-- Skipped items -->
      <div v-if="skippedItems.length > 0" class="completion-section">
        <div class="section-divider-label">{{ t('tour.skipped') }}</div>
        <ul class="completion-list">
          <li v-for="item in skippedItems" :key="item.label" class="completion-list-item skipped">
            <RouterLink :to="item.link" class="skipped-link" @click.prevent="emit('done')">
              <span class="list-label">{{ item.label }}</span>
              <span class="list-arrow">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M6 3l5 5-5 5" />
                </svg>
              </span>
            </RouterLink>
          </li>
        </ul>
      </div>

      <button type="button" class="completion-btn" @click="emit('done')">
        {{ t('tour.goToDashboard') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.completion-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-tour-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.75);
}

.completion-card {
  max-width: 480px;
  width: 90%;
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  border-radius: 16px;
  padding: 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

/* Animated checkmark icon */
.completion-icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  border: 2px solid var(--accent-emerald);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
  animation: pulse-ring 2s ease-in-out infinite;
}

.completion-icon svg {
  width: 32px;
  height: 32px;
  color: var(--accent-emerald);
}

@keyframes pulse-ring {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(0, 255, 136, 0);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(0, 255, 136, 0.4);
  }
}

@media (prefers-reduced-motion: reduce) {
  .completion-icon {
    animation: none;
  }
}

.completion-heading {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.completion-subtext {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 24px;
}

.completion-section {
  width: 100%;
  margin-bottom: 16px;
}

.section-divider-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: 8px;
  text-align: left;
}

.completion-list {
  list-style: none;
  width: 100%;
}

.completion-list-item {
  padding: 6px 0;
  display: flex;
  align-items: center;
  gap: 10px;
  text-align: left;
}

.list-icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
}

.configured-icon {
  color: var(--accent-emerald);
}

.list-label {
  font-size: 14px;
  color: var(--text-primary);
}

.skipped-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 6px 8px;
  border-radius: 6px;
  text-decoration: none;
  color: var(--text-tertiary);
  transition: background var(--transition-fast), color var(--transition-fast);
}

.skipped-link:hover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.skipped-link .list-label {
  color: inherit;
  font-size: 14px;
}

.list-arrow {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.list-arrow svg {
  width: 100%;
  height: 100%;
}

.completion-btn {
  width: 100%;
  height: 40px;
  margin-top: 8px;
  background: var(--accent-cyan);
  color: var(--text-on-accent);
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: filter var(--transition-fast);
}

.completion-btn:hover {
  filter: brightness(1.1);
}
</style>
