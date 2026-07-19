import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { ValidateEnv } from '@julr/vite-plugin-validate-env'
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  const allowedHosts = env.VITE_ALLOWED_HOSTS?.split(',').filter(Boolean) || []
  // Dev server binds to localhost by default — the Vite proxy forwards
  // /api/v1 to the ai-accounts sidecar (which manages CLI credentials and
  // auth tokens). Binding to 0.0.0.0 would expose those endpoints to the
  // LAN. Opt in explicitly with VITE_HOST=0.0.0.0 when you really need
  // LAN access (demos, headless VMs); also set VITE_ALLOWED_HOSTS and
  // AI_ACCOUNTS_API_KEY in that mode so the proxy isn't unauthenticated.
  const host = env.VITE_HOST || '127.0.0.1'

  return {
    plugins: [
      vue(),
      ValidateEnv({ configFile: 'src/env' }),
      VueI18nPlugin({
        include: resolve(dirname(fileURLToPath(import.meta.url)), './src/locales/**'),
      }),
    ],
    server: {
      host,
      port: 3000,
      strictPort: true,
      allowedHosts: allowedHosts.length ? allowedHosts : true,
      proxy: {
        '/api/v1': {
          target: 'http://127.0.0.1:20001',
          changeOrigin: true
        },
        // /api/version, /api/check-backend, /api/validate-path migrated
        // in wave 45. /api/auth/* migrated in waves 32-33+38+43.
        '/api/version': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/check-backend': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/validate-path': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/auth': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/activity-feed': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/models/pricing': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /api/skills/* (incl. /conversations) + /api/skill-sets/* — wave 57.
        '/api/skills': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/skill-sets': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/settings': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // Wave 79: every /api/* route is on Litestar — Flask has no /api handlers left.
        '/api': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        // /admin/rbac was migrated to the Litestar app on :20002 in waves
        // 23-25. More-specific keys take precedence over /admin so the
        // catch-all routes the rest to Flask.
        '/admin/rbac': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        '/admin/bots/sla': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/bots/memory + /admin/bots/{id}/memory/* — wave 65.
        '/admin/bots/memory': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '^/admin/bots/[^/]+/memory': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/bookmarks/* + /admin/prompt-snippets/* + /admin/scope-filters/* + /admin/trigger-conditions/* — wave 65.
        '/admin/bookmarks': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/prompt-snippets': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/scope-filters': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/trigger-conditions': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 66 — marketplaces + integrations admin + audit + pr_reviews.
        '/admin/marketplaces': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/integrations': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/audit': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/pr-reviews': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 67 — products + analytics + findings + reports/digests + config_export.
        '/admin/products': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/analytics': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/reports': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/findings': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 68 — knowledge_graph + collaborative + campaigns + execution_tagging + pr_assignment.
        '/admin/campaigns': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/execution-tags': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/execution-tagging': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/comments': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/pr-assignment': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/executions/{id}/viewers + /comments — collaborative subroutes (executions still on Flask).
        '^/admin/executions/[^/]+/(viewers|comments)': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 69 — monitoring + health_monitor + orchestration + onboarding + repo_bot_defaults + bot_pipes.
        '/admin/monitoring': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/health-monitor': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/orchestration': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/onboarding': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/repo-bot-defaults': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/bot-pipes': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 70 — agent_memory + bulk + replay + conversation_branches.
        '/admin/bulk': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/replay-comparisons': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/diff-context': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/branches': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/conversations': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 75 + 78 — /admin/executions/* + SSE all on Litestar.
        '/admin/executions': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        '^/admin/triggers/[^/]+/executions': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 76 + 78 — /api/setup/* + SSE all on Litestar.
        '/api/setup': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 76 — chunks + super_agent messages/chat (CRUD); SSE streams stay on Flask.
        '/admin/chunked-executions': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '^/admin/bots/[^/]+/run-chunked$': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 76 + 78 — super-agent message + chat (CRUD + streams) all on Litestar.
        '^/admin/super-agents/[^/]+/messages': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        '^/admin/super-agents/[^/]+/sessions/[^/]+/chat': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // /admin/teams/generate (POST async) + /generate/{id} + /generate/stream — all Litestar.
        '^/admin/teams/generate(/.*)?$': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 77 — GitHub webhook + OAuth callback proxy + generic webhook.
        '/api/webhooks/github': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/oauth-callback': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 71 — sketches + agent_conversations CRUD + plugin_exports.
        '/admin/sketches': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/plugin-exports': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 71 + 72 + 78 — every conversation namespace (CRUD + /stream) goes to Litestar.
        '^/api/(plugins|commands|hooks|rules|agents)/conversations': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 73 — utility leftover + /admin/backends/* (CRUD; /stream + test stream stay on Flask).
        '/api/validate-github-url': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/resolve-issues': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/discover-skills': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/browse-directory': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/create-directory': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 73 + 78 — /admin/backends/* (CRUD + SSE streams) all on Litestar.
        '/admin/backends': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 74 + 78 — /api/projects/* GRD (CRUD + SSE streams) all on Litestar.
        '/api/projects': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        '/admin/analytics/cross-team-insights': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/analytics/scheduling-suggestions': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/execution-search': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/rotation': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/specialized-bots': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/bot-templates': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/quality': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/scheduler': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/budgets': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/agents': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/traces': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/rules': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/plugins': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/hooks': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/commands': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/workflows': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/super-agents': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/super-agent-exports': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/system': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/secrets': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/gitops': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/version-pins': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/retention-policies': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/triggers/* (and nested /payload-transformer) — wave 52.
        '/admin/triggers': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/teams/* + nested members/assignments/connections/edges — wave 53.
        '/admin/teams': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/projects/* + nested skills/installations/team-edges/mcp-servers — wave 55+56.
        '/admin/projects': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/mcp-servers/* — wave 56.
        '/admin/mcp-servers': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // Wave 79: every /admin/* route is on Litestar — Flask has no /admin handlers left.
        '/admin': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        // /health/* migrated to Litestar in wave 37.
        '/health': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        // Wave 80: Flask retired. /docs + /openapi were flask-openapi3
        // paths; Litestar serves the spec at /schema (+ /schema/swagger,
        // /schema/redoc). Hand-link from frontend if needed.
        '/schema': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        }
      }
    },
    preview: {
      port: 3000,
      proxy: {
        '/api/v1': {
          target: 'http://127.0.0.1:20001',
          changeOrigin: true
        },
        // /api/version, /api/check-backend, /api/validate-path migrated
        // in wave 45. /api/auth/* migrated in waves 32-33+38+43.
        '/api/version': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/check-backend': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/validate-path': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/auth': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/activity-feed': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/models/pricing': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /api/skills/* (incl. /conversations) + /api/skill-sets/* — wave 57.
        '/api/skills': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/skill-sets': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/settings': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // Wave 79: every /api/* route is on Litestar — Flask has no /api handlers left.
        '/api': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        // /admin/rbac was migrated to the Litestar app on :20002 in waves
        // 23-25. More-specific keys take precedence over /admin so the
        // catch-all routes the rest to Flask.
        '/admin/rbac': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        '/admin/bots/sla': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/bots/memory + /admin/bots/{id}/memory/* — wave 65.
        '/admin/bots/memory': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '^/admin/bots/[^/]+/memory': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/bookmarks/* + /admin/prompt-snippets/* + /admin/scope-filters/* + /admin/trigger-conditions/* — wave 65.
        '/admin/bookmarks': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/prompt-snippets': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/scope-filters': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/trigger-conditions': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 66 — marketplaces + integrations admin + audit + pr_reviews.
        '/admin/marketplaces': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/integrations': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/audit': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/pr-reviews': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 67 — products + analytics + findings + reports/digests + config_export.
        '/admin/products': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/analytics': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/reports': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/findings': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 68 — knowledge_graph + collaborative + campaigns + execution_tagging + pr_assignment.
        '/admin/campaigns': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/execution-tags': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/execution-tagging': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/comments': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/pr-assignment': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/executions/{id}/viewers + /comments — collaborative subroutes (executions still on Flask).
        '^/admin/executions/[^/]+/(viewers|comments)': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 69 — monitoring + health_monitor + orchestration + onboarding + repo_bot_defaults + bot_pipes.
        '/admin/monitoring': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/health-monitor': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/orchestration': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/onboarding': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/repo-bot-defaults': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/bot-pipes': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 70 — agent_memory + bulk + replay + conversation_branches.
        '/admin/bulk': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/replay-comparisons': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/diff-context': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/branches': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/conversations': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 75 + 78 — /admin/executions/* + SSE all on Litestar.
        '/admin/executions': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        '^/admin/triggers/[^/]+/executions': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 76 + 78 — /api/setup/* + SSE all on Litestar.
        '/api/setup': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 76 — chunks + super_agent messages/chat (CRUD); SSE streams stay on Flask.
        '/admin/chunked-executions': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '^/admin/bots/[^/]+/run-chunked$': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 76 + 78 — super-agent message + chat (CRUD + streams) all on Litestar.
        '^/admin/super-agents/[^/]+/messages': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        '^/admin/super-agents/[^/]+/sessions/[^/]+/chat': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // /admin/teams/generate (POST async) + /generate/{id} + /generate/stream — all Litestar.
        '^/admin/teams/generate(/.*)?$': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 77 — GitHub webhook + OAuth callback proxy + generic webhook.
        '/api/webhooks/github': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/oauth-callback': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 71 — sketches + agent_conversations CRUD + plugin_exports.
        '/admin/sketches': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/plugin-exports': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 71 + 72 + 78 — every conversation namespace (CRUD + /stream) goes to Litestar.
        '^/api/(plugins|commands|hooks|rules|agents)/conversations': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 73 — utility leftover + /admin/backends/* (CRUD; /stream + test stream stay on Flask).
        '/api/validate-github-url': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/resolve-issues': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/discover-skills': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/browse-directory': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/api/create-directory': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // wave 73 + 78 — /admin/backends/* (CRUD + SSE streams) all on Litestar.
        '/admin/backends': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        // wave 74 + 78 — /api/projects/* GRD (CRUD + SSE streams) all on Litestar.
        '/api/projects': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true,
        },
        '/admin/analytics/cross-team-insights': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/analytics/scheduling-suggestions': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/execution-search': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/rotation': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/specialized-bots': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/bot-templates': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/quality': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/scheduler': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/budgets': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/agents': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/traces': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/rules': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/plugins': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/hooks': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/commands': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/workflows': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/super-agents': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/super-agent-exports': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/system': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/secrets': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/gitops': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/version-pins': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        '/admin/retention-policies': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/triggers/* (and nested /payload-transformer) — wave 52.
        '/admin/triggers': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/teams/* + nested members/assignments/connections/edges — wave 53.
        '/admin/teams': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/projects/* + nested skills/installations/team-edges/mcp-servers — wave 55+56.
        '/admin/projects': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // /admin/mcp-servers/* — wave 56.
        '/admin/mcp-servers': { target: 'http://127.0.0.1:20000', changeOrigin: true },
        // Wave 79: every /admin/* route is on Litestar — Flask has no /admin handlers left.
        '/admin': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        // /health/* migrated to Litestar in wave 37.
        '/health': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        // Wave 80: Flask retired. /docs + /openapi were flask-openapi3
        // paths; Litestar serves the spec at /schema (+ /schema/swagger,
        // /schema/redoc). Hand-link from frontend if needed.
        '/schema': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        }
      }
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: {
        output: {
          manualChunks(id) {
            // CSS modules must NEVER be pinned to a JS chunk: main.ts imports
            // only @ai-accounts/vue-styled/styles.css, and pinning that CSS id
            // to the 'ai-accounts-vue-styled' JS chunk made the ENTRY statically
            // depend on the whole ~1.1 MB package at boot.
            if (id.endsWith('.css')) {
              return undefined
            }
            // file: deps from sibling ai-accounts repo come in via
            // node_modules/@ai-accounts/*. Split each so the largest
            // (vue-styled, ~1MB) doesn't bloat any single chunk.
            if (id.includes('@ai-accounts/vue-styled')) {
              return 'ai-accounts-vue-styled'
            }
            if (id.includes('@ai-accounts/vue-headless')) {
              return 'ai-accounts-vue-headless'
            }
            if (id.includes('@ai-accounts/ts-core')) {
              return 'ai-accounts-ts-core'
            }

            if (id.includes('node_modules')) {
              // v0.6.0 perf: split the big vendors into named cache-stable
              // chunks.
              if (id.includes('chart.js') || id.includes('chartjs-adapter-date-fns') || id.includes('date-fns')) {
                return 'vendor-chart'
              }
              if (id.includes('highlight.js')) {
                return 'vendor-highlight'
              }
              if (id.includes('@vue-flow') || id.includes('@dagrejs/dagre')) {
                return 'vendor-vue-flow'
              }
              if (id.includes('/marked/') || id.includes('dompurify')) {
                return 'vendor-markdown'
              }
              if (id.includes('/vue-router/') || id.includes('/@vue/devtools')) {
                return 'vendor-vue-router'
              }
              if (id.includes('/vue/dist/') || id.includes('/@vue/runtime') || id.includes('/@vue/reactivity') || id.includes('/@vue/shared')) {
                return 'vendor-vue'
              }
              if (id.includes('/axios/') || id.includes('/follow-redirects/') || id.includes('/form-data/')) {
                return 'vendor-axios'
              }
              if (id.includes('@msgpack/msgpack') || id.includes('msgpack-lite')) {
                return 'vendor-msgpack'
              }
              if (id.includes('/lodash')) {
                return 'vendor-lodash'
              }
              // Everything else: let rollup chunk by the import graph. The old
              // blanket `return 'vendor-core'` glued every remaining
              // node_module — including libraries used only by lazy pages —
              // into ONE 2.6 MB chunk that the entry imported at boot (it
              // needed vue-i18n from it, so it got xstate, driver.js,
              // html-to-image, sortable, ... with it).
              return undefined
            }
          }
        }
      }
    }
  }
})
