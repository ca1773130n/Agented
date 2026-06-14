<script setup lang="ts">
/**
 * HarnessPanelHost (REQ-16) — tabbed host for the seven GRD-route panels.
 *
 * Reuses the repo's existing TabbedViewHost (sidebar-prune work) rather than
 * hand-rolling tabs. TabbedViewHost renders the active tab's component with no
 * props, so each panel is wrapped in a tiny render closure that binds the
 * current projectId. Wrappers are markRaw'd (TabbedViewHost contract) to avoid
 * Vue proxying them.
 */
import { computed, h, markRaw, type Component } from 'vue';
import TabbedViewHost from '../../base/TabbedViewHost.vue';
import HealthPanel from './panels/HealthPanel.vue';
import ThinkPanel from './panels/ThinkPanel.vue';
import DeadEndsPanel from './panels/DeadEndsPanel.vue';
import GenomePanel from './panels/GenomePanel.vue';
import VerifyPanel from './panels/VerifyPanel.vue';
import ReflectionsPanel from './panels/ReflectionsPanel.vue';
import HarnessRoundsPanel from './panels/HarnessRoundsPanel.vue';
import EvolvePanel from './panels/EvolvePanel.vue';

const props = defineProps<{ projectId: string }>();

function bind(panel: Component, projectId: string): Component {
  return markRaw({
    name: 'HarnessPanelWrapper',
    render: () => h(panel, { projectId }),
  });
}

const tabs = computed(() => [
  { key: 'health', labelKey: 'surface.harness.panels.health.tab', component: bind(HealthPanel, props.projectId) },
  { key: 'think', labelKey: 'surface.harness.panels.think.tab', component: bind(ThinkPanel, props.projectId) },
  { key: 'dead-ends', labelKey: 'surface.harness.panels.deadEnds.tab', component: bind(DeadEndsPanel, props.projectId) },
  { key: 'genome', labelKey: 'surface.harness.panels.genome.tab', component: bind(GenomePanel, props.projectId) },
  { key: 'verify', labelKey: 'surface.harness.panels.verify.tab', component: bind(VerifyPanel, props.projectId) },
  { key: 'reflections', labelKey: 'surface.harness.panels.reflections.tab', component: bind(ReflectionsPanel, props.projectId) },
  { key: 'harness-rounds', labelKey: 'grdHarnessRounds.title', component: bind(HarnessRoundsPanel, props.projectId) },
  { key: 'evolve', labelKey: 'surface.harness.panels.evolve.tab', component: bind(EvolvePanel, props.projectId) },
]);
</script>

<template>
  <div class="harness-panel-host card">
    <TabbedViewHost
      :tabs="tabs"
      tablist-label-key="surface.harness.tablistLabel"
      id-prefix="harness-panels"
    />
  </div>
</template>

<style scoped>
.harness-panel-host { border: 1px solid var(--border-default); border-radius: 8px; padding: 1rem 1.25rem; }
</style>
