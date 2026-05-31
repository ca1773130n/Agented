<!--
  DashboardsPage — repurposed as the 4-lane index for PR-D.

  Replaces the previous 13-tile launcher with a focused 4-tile lane grid
  (Quality / Cost / Health / Activity) and a small "Deep links" row for
  the now-hidden Token Usage and Scheduling specifics so existing inbound
  references (router.push by name) still resolve to something obvious.
-->
<script setup lang="ts">
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const { t } = useI18n();
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
    name: t('dashboards.lanes.quality.name'),
    routeName: 'dashboards-quality',
    description: t('dashboards.lanes.quality.description'),
    accent: 'var(--accent-crimson)',
    gradient: 'linear-gradient(135deg, var(--accent-crimson), var(--accent-amber))',
    icon: '⬡',
  },
  {
    name: t('dashboards.lanes.cost.name'),
    routeName: 'dashboards-cost',
    description: t('dashboards.lanes.cost.description'),
    accent: 'var(--accent-amber)',
    gradient: 'linear-gradient(135deg, var(--accent-amber), var(--accent-emerald))',
    icon: '◇',
  },
  {
    name: t('dashboards.lanes.health.name'),
    routeName: 'dashboards-health',
    description: t('dashboards.lanes.health.description'),
    accent: 'var(--accent-emerald)',
    gradient: 'linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))',
    icon: '⊕',
  },
  {
    name: t('dashboards.lanes.activity.name'),
    routeName: 'dashboards-activity',
    description: t('dashboards.lanes.activity.description'),
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
    label: t('dashboards.deepLinks.tokenUsage.label'),
    routeName: 'dashboards-cost',
    hash: '#token-usage',
    description: t('dashboards.deepLinks.tokenUsage.description'),
  },
  {
    label: t('dashboards.deepLinks.scheduling.label'),
    routeName: 'dashboards-activity',
    hash: '#scheduling',
    description: t('dashboards.deepLinks.scheduling.description'),
  },
  {
    label: t('dashboards.deepLinks.serviceHealth.label'),
    routeName: 'dashboards-health',
    hash: '#service-health',
    description: t('dashboards.deepLinks.serviceHealth.description'),
  },
];

interface OrgTile {
  label: string;
  routeName: string;
  description: string;
  accent: string;
}

const orgTiles: OrgTile[] = [
  {
    label: t('dashboards.orgTiles.products.label'),
    routeName: 'products-summary',
    description: t('dashboards.orgTiles.products.description'),
    accent: 'var(--accent-violet)',
  },
  {
    label: t('dashboards.orgTiles.projects.label'),
    routeName: 'projects-summary',
    description: t('dashboards.orgTiles.projects.description'),
    accent: 'var(--accent-cyan)',
  },
  {
    label: t('dashboards.orgTiles.teams.label'),
    routeName: 'teams-summary',
    description: t('dashboards.orgTiles.teams.description'),
    accent: 'var(--accent-emerald)',
  },
  {
    label: t('dashboards.orgTiles.agents.label'),
    routeName: 'agents-summary',
    description: t('dashboards.orgTiles.agents.description'),
    accent: 'var(--accent-amber)',
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
        orgTileCount: orgTiles.length,
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

function openOrgTile(tile: OrgTile) {
  router.push({ name: tile.routeName });
}
</script>

<template>
  <div class="dashboards-page">
    <PageHeader :title="t('dashboards.title')" :subtitle="t('dashboards.subtitle')" />

    <section class="lane-tiles" :aria-label="t('dashboards.ariaLanes')">
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

    <section class="org-tiles" :aria-label="t('dashboards.ariaOrgTiles')">
      <h2 class="org-tiles__title">{{ t('dashboards.orgOverview') }}</h2>
      <div class="org-tiles__grid">
        <button
          v-for="tile in orgTiles"
          :key="tile.routeName"
          class="org-tile"
          :data-testid="`org-tile-${tile.routeName}`"
          :style="{ '--tile-accent': tile.accent }"
          @click="openOrgTile(tile)"
        >
          <span class="org-tile__label">{{ tile.label }}</span>
          <span class="org-tile__desc">{{ tile.description }}</span>
        </button>
      </div>
    </section>

    <section class="deep-links" :aria-label="t('dashboards.ariaDeepLinks')">
      <h2 class="deep-links__title">{{ t('dashboards.quickLinks') }}</h2>
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

.org-tiles { display: flex; flex-direction: column; gap: 12px; }
.org-tiles__title { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-tertiary); margin: 0; }
.org-tiles__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }

.org-tile {
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
.org-tile:hover { border-color: var(--tile-accent); }
.org-tile__label { font-size: 13px; font-weight: 600; }
.org-tile__desc { font-size: 11px; color: var(--text-tertiary); }
</style>
