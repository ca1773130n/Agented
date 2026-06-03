<script setup lang="ts">
/**
 * Execution Tools — collapses four execution-observability surfaces that each
 * had a standalone sidebar slot (Search, Tagging, Replay & Diff, Annotations)
 * into one tabbed page. Each tab renders its original view unchanged (only the
 * active tab mounts); the old routes redirect here with `?tab=`.
 */
import { markRaw } from 'vue';
import TabbedViewHost from '../components/base/TabbedViewHost.vue';
import SearchView from './ExecutionSearchPage.vue';
import TaggingView from './ExecutionTaggingPage.vue';
import ReplayView from './ExecutionReplayDiff.vue';
import AnnotationsView from './ExecutionAnnotation.vue';

// Reuse the existing, already-localized sidebar labels for the tabs.
const tabs = [
  { key: 'search', labelKey: 'nav.executionSearch', component: markRaw(SearchView) },
  { key: 'tagging', labelKey: 'nav.executionTagging', component: markRaw(TaggingView) },
  { key: 'replay', labelKey: 'nav.replayDiff', component: markRaw(ReplayView) },
  { key: 'annotations', labelKey: 'nav.annotations', component: markRaw(AnnotationsView) },
];
</script>

<template>
  <TabbedViewHost :tabs="tabs" tablist-label-key="nav.executionTools" id-prefix="execution-tools" />
</template>
