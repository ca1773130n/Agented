<!--
  DashboardsPage — repurposed as the 4-lane index for PR-D.

  Replaces the previous 13-tile launcher with a focused 4-tile lane grid
  (Quality / Cost / Health / Activity) and a small "Deep links" row for
  the now-hidden Token Usage and Scheduling specifics so existing inbound
  references (router.push by name) still resolve to something obvious.
-->
<script setup lang="ts">
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();

interface LaneTile {
  name: string;
  routeName: string;
  description: string;
  accent: string;
  gradient: string;
  icon: string;
}

const lanes: LaneTile[] = [
  {
    name: 'Quality',
    routeName: 'dashboards-quality',
    description: 'Security findings, PR review status, and execution anomaly detection.',
    accent: 'var(--accent-crimson)',
    gradient: 'linear-gradient(135deg, var(--accent-crimson), var(--accent-amber))',
    icon: '⬡',
  },
  {
    name: 'Cost',
    routeName: 'dashboards-cost',
    description: 'Token usage, spend trend, budgets, and rate-limit windows.',
    accent: 'var(--accent-amber)',
    gradient: 'linear-gradient(135deg, var(--accent-amber), var(--accent-emerald))',
    icon: '◇',
  },
  {
    name: 'Health',
    routeName: 'dashboards-health',
    description: 'System health, per-bot rollups, and AI-service status.',
    accent: 'var(--accent-emerald)',
    gradient: 'linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))',
    icon: '⊕',
  },
  {
    name: 'Activity',
    routeName: 'dashboards-activity',
    description: 'Scheduling, execution queue, volume / success trends, and team reports.',
    accent: 'var(--accent-cyan)',
    gradient: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-violet))',
    icon: '◈',
  },
];

interface DeepLink {
  label: string;
  routeName: string;
  hash?: string;
  description: string;
}

const deepLinks: DeepLink[] = [
  {
    label: 'Token Usage',
    routeName: 'dashboards-cost',
    hash: '#token-usage',
    description: 'Jump straight to Cost — Token Usage card.',
  },
  {
    label: 'Scheduling',
    routeName: 'dashboards-activity',
    hash: '#scheduling',
    description: 'Jump to the Scheduling card in Activity.',
  },
  {
    label: 'Service Health',
    routeName: 'dashboards-health',
    hash: '#service-health',
    description: 'Jump to AI-service account health in Health.',
  },
];

useWebMcpTool({
  name: 'agented_dashboards_get_state',
  description: 'Returns the current state of the DashboardsPage (4-lane index)',
  page: 'DashboardsPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'DashboardsPage',
        layout: 'lanes-v1',
        laneCount: lanes.length,
        deepLinkCount: deepLinks.length,
      }),
    }],
  }),
});

function openLane(tile: LaneTile) {
  router.push({ name: tile.routeName });
}

function openDeepLink(link: DeepLink) {
  router.push({ name: link.routeName, hash: link.hash });
}
</script>

<template>
  <div class="dashboards-page">
    <PageHeader title="Dashboards" subtitle="Four lanes, one operator console" />

    <section class="lane-tiles" aria-label="Dashboard lanes">
      <button
        v-for="tile in lanes"
        :key="tile.routeName"
        class="lane-tile"
        :data-testid="`lane-tile-${tile.routeName}`"
        :style="{ '--tile-gradient': tile.gradient, '--tile-accent': tile.accent }"
        @click="openLane(tile)"
      >
        <span class="lane-tile__icon" aria-hidden="true">{{ tile.icon }}</span>
        <span class="lane-tile__name">{{ tile.name }}</span>
        <span class="lane-tile__desc">{{ tile.description }}</span>
      </button>
    </section>

    <section class="deep-links" aria-label="Quick deep links">
      <h2 class="deep-links__title">Quick links</h2>
      <div class="deep-links__grid">
        <button
          v-for="link in deepLinks"
          :key="link.label + (link.hash || '')"
          class="deep-link"
          :data-testid="`deep-link-${link.routeName}${link.hash ?? ''}`"
          @click="openDeepLink(link)"
        >
          <span class="deep-link__label">{{ link.label }}</span>
          <span class="deep-link__desc">{{ link.description }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.dashboards-page { display: flex; flex-direction: column; gap: 32px; width: 100%; }

.lane-tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}

.lane-tile {
  position: relative;
  text-align: left;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  cursor: pointer;
  color: var(--text-primary);
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 140px;
  overflow: hidden;
  transition: border-color 0.15s, transform 0.15s;
}

.lane-tile::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--tile-gradient);
  opacity: 0.08;
  pointer-events: none;
  transition: opacity 0.2s;
}

.lane-tile:hover { border-color: var(--tile-accent); transform: translateY(-2px); }
.lane-tile:hover::before { opacity: 0.14; }

.lane-tile__icon { font-size: 22px; color: var(--tile-accent); }
.lane-tile__name { font-size: 16px; font-weight: 600; }
.lane-tile__desc { font-size: 12px; color: var(--text-tertiary); line-height: 1.5; }

.deep-links { display: flex; flex-direction: column; gap: 12px; }
.deep-links__title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-tertiary); margin: 0; }
.deep-links__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }

.deep-link {
  display: flex; flex-direction: column; gap: 4px;
  padding: 14px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  text-align: left;
  cursor: pointer;
  color: var(--text-primary);
  transition: border-color 0.15s;
}
.deep-link:hover { border-color: var(--accent-cyan); }
.deep-link__label { font-size: 13px; font-weight: 600; }
.deep-link__desc { font-size: 11px; color: var(--text-tertiary); }
</style>
