<script setup lang="ts">
/**
 * Trigger Tools — collapses five trigger-scoped authoring/test surfaces that
 * each had a standalone Triggers-submenu slot into one tabbed page:
 *   Conditions (conditional-trigger-rules), Natural Language (nl rule editor),
 *   Schedule (visual cron wizard), Payload (webhook payload transformer),
 *   Dry Run (bot dry-run).
 * Each tab renders its original view unchanged (only the active tab mounts);
 * the old routes redirect here with `?tab=`.
 */
import { markRaw } from 'vue';
import TabbedViewHost from '../components/base/TabbedViewHost.vue';
import ConditionsView from './ConditionalTriggerRulesPage.vue';
import NlView from './NLTriggerRuleEditor.vue';
import ScheduleView from './VisualCronWizard.vue';
import PayloadView from './WebhookPayloadTransformerPage.vue';
import DryRunView from './BotDryRun.vue';

// Reuse the existing, already-localized sidebar labels for the tabs.
const tabs = [
  { key: 'conditions', labelKey: 'nav.triggerConditions', component: markRaw(ConditionsView) },
  { key: 'nl', labelKey: 'nav.nlRuleEditor', component: markRaw(NlView) },
  { key: 'schedule', labelKey: 'nav.nlCronBuilder', component: markRaw(ScheduleView) },
  { key: 'payload', labelKey: 'nav.payloadTransformer', component: markRaw(PayloadView) },
  { key: 'dry-run', labelKey: 'nav.botDryRun', component: markRaw(DryRunView) },
];
</script>

<template>
  <TabbedViewHost :tabs="tabs" tablist-label-key="nav.triggerTools" id-prefix="trigger-tools" />
</template>
