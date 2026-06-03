<script setup lang="ts">
/**
 * Help — home for the static developer-docs / setup surfaces that don't earn
 * their own sidebar slot: the Plugin SDK reference and the GitHub Actions
 * setup guide. Composed as tabs via TabbedViewHost; the old routes redirect
 * here with `?tab=`.
 */
import { markRaw } from 'vue';
import TabbedViewHost from '../components/base/TabbedViewHost.vue';
import PluginSdkView from './PluginSdkPage.vue';
import GitHubActionsView from './GitHubActionsPage.vue';

const tabs = [
  { key: 'plugin-sdk', labelKey: 'nav.pluginSdk', component: markRaw(PluginSdkView) },
  { key: 'github-actions', labelKey: 'nav.githubActions', component: markRaw(GitHubActionsView) },
];
</script>

<template>
  <TabbedViewHost :tabs="tabs" tablist-label-key="nav.help" id-prefix="help" />
</template>
