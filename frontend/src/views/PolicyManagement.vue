<script setup lang="ts">
/**
 * PolicyManagement (phase 23, 23-05).
 *
 * Operator page hosting the policy CRUD editor. The PolicyAskCard is rendered
 * inline within session panels (driven by the `policy_ask` SSE event), so this
 * page is the authoring surface.
 */
import { useI18n } from 'vue-i18n';
import PolicyEditor from '../components/policy/PolicyEditor.vue';

const { t } = useI18n();
</script>

<template>
  <main class="pm-page">
    <h1 class="pm-title">{{ t('policy.title') }}</h1>
    <PolicyEditor />
  </main>
</template>

<style scoped>
.pm-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px;
  font-family: var(--font-family, 'Geist', system-ui, sans-serif);
}
.pm-title {
  font-size: 1.4rem;
  margin: 0 0 18px;
  color: var(--color-text, #e6e6e6);
}
</style>
