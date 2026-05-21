import type { RouteRecordRaw } from 'vue-router';

export const agentsExtRoutes: RouteRecordRaw[] = [
  // Agent Capability Matrix (Feature 17)
  {
    path: '/agents/capability-matrix',
    name: 'agent-capability-matrix',
    component: () => import('../../views/AgentCapabilityMatrix.vue'),
    meta: { title: 'Agent Capability Matrix' },
  },
  // Agent Quality Scoring (Feature 14)
  {
    path: '/agents/quality-scoring',
    name: 'agent-quality-scoring',
    component: () => import('../../views/AgentQualityScoringPage.vue'),
    meta: { title: 'Agent Quality Scoring' },
  },
  // Agent Skill Auto-Discovery (Feature 28)
  {
    path: '/agents/skill-discovery',
    name: 'agent-skill-discovery',
    component: () => import('../../views/AgentSkillDiscoveryPage.vue'),
    meta: { title: 'Skill Auto-Discovery' },
  },
  // Multi-Agent Collaboration Mode
  {
    path: '/bots/multi-agent',
    name: 'multi-agent-collaboration',
    component: () => import('../../views/MultiAgentCollaboration.vue'),
    meta: { title: 'Multi-Agent Collaboration' },
  },
  // Visual Skill Composer (feature 31)
  {
    path: '/skills/composer',
    name: 'visual-skill-composer',
    component: () => import('../../views/VisualSkillComposerPage.vue'),
    meta: { title: 'Visual Skill Composer' },
  },
  // Skill Marketplace & Sharing (item 10) — redirect to the unified
  // Marketplace's Skills tab (PR-C). The SkillMarketplacePage view was
  // deleted; its installed+available join is now reachable from the
  // Settings → Plugin Marketplaces admin tab.
  {
    path: '/skills/marketplace',
    name: 'skill-marketplace',
    redirect: () => ({ name: 'marketplace', query: { type: 'skills' } }),
  },
  // Skill & Plugin Version Pinning (feature 34)
  {
    path: '/settings/version-pinning',
    name: 'skill-version-pinning',
    component: () => import('../../views/SkillVersionPinningPage.vue'),
    meta: { title: 'Skill & Plugin Version Pinning' },
  },
];
