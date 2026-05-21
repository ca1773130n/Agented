<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import MarketplacePlugins from './marketplace/MarketplacePlugins.vue';
import MarketplaceSkills from './marketplace/MarketplaceSkills.vue';
import MarketplaceMcpServers from './marketplace/MarketplaceMcpServers.vue';
import MarketplaceSuperAgents from './marketplace/MarketplaceSuperAgents.vue';

type TabKey = 'plugins' | 'skills' | 'mcp-servers' | 'super-agents';

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'plugins', label: 'Plugins' },
  { key: 'skills', label: 'Skills' },
  { key: 'mcp-servers', label: 'MCP Servers' },
  { key: 'super-agents', label: 'SuperAgents' },
];

const route = useRoute();
const router = useRouter();

const activeTab = computed<TabKey>(() => {
  const raw = String(route.query.type ?? '');
  const match = TABS.find((t) => t.key === raw);
  return match ? match.key : 'plugins';
});

function selectTab(key: TabKey) {
  if (activeTab.value === key) return;
  // Replace (not push) to avoid history-stack pollution from tab clicks.
  router.replace({ name: 'marketplace', query: { type: key } });
}
</script>

<template>
  <div class="marketplace-page">
    <PageHeader
      title="Marketplace"
      subtitle="Discover plugins, skills, MCP servers, and SuperAgents across registered marketplaces."
    />

    <div class="tab-strip" role="tablist" aria-label="Marketplace artifact type">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        role="tab"
        :aria-selected="activeTab === tab.key"
        :class="['tab-btn', { active: activeTab === tab.key }]"
        @click="selectTab(tab.key)"
      >
        {{ tab.label }}
      </button>
    </div>

    <div class="tab-body" role="tabpanel">
      <MarketplacePlugins v-if="activeTab === 'plugins'" />
      <MarketplaceSkills v-else-if="activeTab === 'skills'" />
      <MarketplaceMcpServers v-else-if="activeTab === 'mcp-servers'" />
      <MarketplaceSuperAgents v-else-if="activeTab === 'super-agents'" />
    </div>
  </div>
</template>

<style scoped>
.marketplace-page {
}

.tab-strip {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border-default);
}

.tab-btn {
  appearance: none;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  color: var(--accent-cyan);
  border-bottom-color: var(--accent-cyan);
}

.tab-body {
  min-height: 200px;
}
</style>
