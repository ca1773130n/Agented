/**
 * Shared mock data for Playwright E2E tests.
 * Covers the 8 mandatory API endpoints that App.vue calls on mount,
 * plus populated entity mocks for CRUD tests.
 */

// --- Global mock responses (empty lists for baseline) ---

export const MOCK_HEALTH = {
  status: 'ok',
  components: {
    database: { status: 'ok' },
    process_manager: {
      status: 'ok',
      active_executions: 0,
      active_execution_ids: [],
    },
  },
};

export const MOCK_VERSION = { version: '0.2.2' };

export const MOCK_TRIGGERS = { triggers: [] };
export const MOCK_PROJECTS = { projects: [] };
export const MOCK_PRODUCTS = { products: [] };
export const MOCK_TEAMS = { teams: [] };
export const MOCK_PLUGINS = { plugins: [] };
export const MOCK_BACKENDS = { backends: [] };

// --- Populated entity mocks for CRUD tests ---

export const MOCK_PRODUCT = {
  id: 'prod-test01',
  name: 'Test Product',
  description: 'E2E test product',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
};

export const MOCK_PROJECT = {
  id: 'proj-test01',
  name: 'Test Project',
  description: 'E2E test project',
  status: 'active',
  github_url: 'https://github.com/test/repo',
  product_id: 'prod-test01',
  created_at: '2026-01-01T00:00:00Z',
};

export const MOCK_TEAM = {
  id: 'team-test01',
  name: 'Test Team',
  description: 'E2E test team',
  topology_type: 'sequential',
  project_id: 'proj-test01',
  created_at: '2026-01-01T00:00:00Z',
  agents: [],
};

export const MOCK_AGENT = {
  id: 'agent-test1',
  name: 'Test Agent',
  role: 'developer',
  description: 'E2E test agent',
  backend_type: 'claude',
  model: 'opus',
  team_id: 'team-test01',
  created_at: '2026-01-01T00:00:00Z',
};

export const MOCK_PLUGIN = {
  id: 'plug-test01',
  name: 'Test Plugin',
  description: 'E2E test plugin',
  version: '1.0.0',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
};

export const MOCK_SKILL = {
  id: 1,
  skill_name: 'test-skill',
  skill_path: '/tmp/test-skill',
  description: 'E2E test skill',
  enabled: 1,
  selected_for_harness: 0,
  created_at: '2026-01-01T00:00:00Z',
};

export const MOCK_BACKEND_ITEM = {
  id: 'claude',
  name: 'Claude',
  type: 'claude',
  installed: true,
  accounts: 1,
  models: ['opus-4', 'sonnet-4'],
};

export const MOCK_TRIGGER = {
  id: 'bot-test01',
  name: 'Test Trigger',
  trigger_source: 'webhook',
  status: 'active',
  prompt_template: 'test',
  backend_type: 'claude',
  detection_keyword: '',
  match_field_path: '',
  match_field_value: '',
  text_field_path: '',
  group_id: 1,
  is_predefined: 0,
  enabled: 1,
  auto_resolve: 0,
  created_at: '2026-01-01T00:00:00Z',
};

// --- Mock data for specific sections ---

export const MOCK_HOOKS = { hooks: [] };
export const MOCK_COMMANDS = { commands: [] };
export const MOCK_RULES = { rules: [] };
export const MOCK_AGENTS = { agents: [] };
export const MOCK_SKILLS = { skills: [] };

export const MOCK_HOOK = {
  id: 1,
  name: 'test-hook',
  description: 'E2E test hook',
  content: 'echo hook',
  hook_type: 'pre',
  project_id: 'proj-test01',
};

export const MOCK_COMMAND = {
  id: 1,
  name: 'test-command',
  description: 'E2E test command',
  content: 'echo command',
  project_id: 'proj-test01',
};

export const MOCK_RULE = {
  id: 1,
  name: 'test-rule',
  description: 'E2E test rule',
  content: 'echo rule',
  is_global: false,
  project_id: 'proj-test01',
};

export const MOCK_ACCOUNTS = { accounts: [] };

export const MOCK_DASHBOARD_SUMMARY = {
  dashboards: [
    { id: 'security', name: 'Security Scan', type: 'security' },
    { id: 'pr-review', name: 'PR Review', type: 'pr-review' },
    { id: 'token-usage', name: 'Token Usage', type: 'token-usage' },
  ],
};
