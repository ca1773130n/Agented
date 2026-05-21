import { createRouter, createWebHistory } from 'vue-router';
import { dashboardRoutes } from './routes/dashboard';
import { agentRoutes } from './routes/agents';
import { teamRoutes } from './routes/teams';
import { productRoutes } from './routes/products';
import { projectRoutes } from './routes/projects';
import { pluginRoutes } from './routes/plugins';
import { skillRoutes } from './routes/skills';
import { workflowRoutes } from './routes/workflows';
import { mcpServerRoutes } from './routes/mcpServers';
import { superAgentRoutes } from './routes/superAgents';
import { marketplaceRoutes } from './routes/marketplace';
import { triggerRoutes } from './routes/triggers';
import { settingsRoutes } from './routes/settings';
import { miscRoutes } from './routes/misc';
import { observabilityRoutes } from './routes/observability';
import { authRoutes } from './routes/auth';
import { aiBackendRoutes } from './routes/aiBackends';
import { botRoutes } from './routes/bots';
import { executionRoutes } from './routes/executions';
import { promptRoutes } from './routes/prompts';
import { githubRoutes } from './routes/github';
import { codeBlockRoutes } from './routes/codeBlocks';
import { notificationRoutes } from './routes/notifications';
import { triggersExtRoutes } from './routes/triggersExt';
import { findingsRoutes } from './routes/findings';
import { reportsRoutes } from './routes/reports';
import { onboardingRoutes } from './routes/onboarding';
import { infraRoutes } from './routes/infra';
import { agentsExtRoutes } from './routes/agentsExt';
import { observabilityExtRoutes } from './routes/observabilityExt';
import { registerGuards } from './guards';

// Extend RouteMeta with Agented-specific fields
declare module 'vue-router' {
  interface RouteMeta {
    /** Entity param key to validate before navigation (e.g., 'teamId') */
    requiresEntity?: string;
    /** Display title for the page, used as document.title suffix */
    title?: string;
    /** Whether the view uses a full-bleed (no-padding) layout */
    fullBleed?: boolean;
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    ...dashboardRoutes,
    ...agentRoutes,
    ...teamRoutes,
    ...productRoutes,
    ...projectRoutes,
    ...pluginRoutes,
    ...skillRoutes,
    ...workflowRoutes,
    ...mcpServerRoutes,
    ...superAgentRoutes,
    ...marketplaceRoutes,
    ...triggerRoutes,
    ...settingsRoutes,
    ...authRoutes,
    ...aiBackendRoutes,
    ...botRoutes,
    ...executionRoutes,
    ...promptRoutes,
    ...githubRoutes,
    ...codeBlockRoutes,
    ...notificationRoutes,
    ...triggersExtRoutes,
    ...findingsRoutes,
    ...reportsRoutes,
    ...onboardingRoutes,
    ...infraRoutes,
    ...agentsExtRoutes,
    ...observabilityExtRoutes,
    ...miscRoutes,
    ...observabilityRoutes,
    // Catch-all 404 route (must be last)
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/NotFoundPage.vue'),
      meta: { title: 'Not Found' },
    },
  ],
});

// Register global navigation guards
registerGuards(router);
