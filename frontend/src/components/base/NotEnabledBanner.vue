<!--
  NotEnabledBanner — shared "Feature not yet enabled in this deployment"
  banner. Extracted from 17 PR-J3 STUB-DEFER views + 3 PR-G surfaces
  (ExecutionQuotaControls, ReportDigestsPage, AnomalyDetectionCard).

  Props:
    - feature  Required. Sentence-leading subject. Rendered as:
               "{{ feature }} is not yet enabled in this deployment."
    - detail   Optional. Secondary line printed under the headline.
               If omitted, the <p> is not rendered.
    - testid   Optional. Overrides the default data-testid
               ("not-enabled-banner"). Used by callers that already had
               surface-specific testids before extraction so their
               existing selectors keep working.

  The visual (dashed border, role=status, info icon) matches the
  PR-J3 / PR-G banner shape exactly so no theming changes ride along
  with this refactor.
-->
<script setup lang="ts">
withDefaults(
  defineProps<{
    feature: string;
    detail?: string;
    testid?: string;
  }>(),
  { testid: 'not-enabled-banner' },
);
</script>

<template>
  <div class="not-enabled-banner" :data-testid="testid" role="status">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
    <div>
      <strong>{{ feature }} is not yet enabled in this deployment.</strong>
      <p v-if="detail">{{ detail }}</p>
    </div>
  </div>
</template>

<style scoped>
.not-enabled-banner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 20px;
  border-radius: 8px;
  background: var(--bg-elevated, rgba(255, 255, 255, 0.04));
  border: 1px dashed var(--border-default, rgba(255, 255, 255, 0.15));
  color: var(--text-secondary);
}
.not-enabled-banner svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: var(--text-tertiary);
  margin-top: 2px;
}
.not-enabled-banner strong {
  display: block;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}
.not-enabled-banner p {
  margin: 0;
  font-size: 0.82rem;
  color: var(--text-tertiary);
}
</style>
