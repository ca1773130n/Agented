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
import { triggerRoutes } from './routes/triggers';
import { settingsRoutes } from './routes/settings';
import { miscRoutes } from './routes/misc';
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
    ...triggerRoutes,
    ...settingsRoutes,
    ...miscRoutes,
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
