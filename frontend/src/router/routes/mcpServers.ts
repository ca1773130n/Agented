import type { RouteRecordRaw } from 'vue-router';

export const mcpServerRoutes: RouteRecordRaw[] = [
  {
    path: '/mcp-servers',
    name: 'mcp-servers',
    component: () => import('../../views/McpServersPage.vue'),
    meta: { title: 'MCP Servers' },
  },
  {
    // Redirect: replaced by unified Marketplace (PR-C).
    path: '/mcp-servers/explore',
    name: 'explore-mcp-servers',
    redirect: () => ({ name: 'marketplace', query: { type: 'mcp-servers' } }),
  },
  {
    path: '/mcp-servers/:mcpServerId',
    name: 'mcp-server-detail',
    component: () => import('../../views/McpServerDetailPage.vue'),
    props: true,
    meta: { title: 'MCP Server Detail', requiresEntity: 'mcpServerId' },
  },
];
