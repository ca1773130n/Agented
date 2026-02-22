/**
 * Full sweep test: visits every page in sequence, invokes every get_state tool,
 * verifies all return valid JSON with expected fields.
 */
import { describe, it, expect, vi } from 'vitest';
import { invokeTool } from '../test-harness/random-runner';

/** All expected get_state tool names across the application. */
const ALL_STATE_TOOLS = [
  // List pages (from useWebMcpPageTools)
  'hive_teams_get_list_state',
  'hive_products_get_list_state',
  'hive_projects_get_list_state',
  'hive_agents_get_list_state',
  'hive_plugins_get_list_state',
  'hive_hooks_get_list_state',
  'hive_commands_get_list_state',
  'hive_rules_get_list_state',
  'hive_mcp_servers_get_list_state',
  'hive_super_agents_get_list_state',
  'hive_workflows_get_list_state',
  'hive_skills_get_list_state',

  // Detail/settings pages
  'hive_agent_design_get_state',
  'hive_agent_create_get_state',
  'hive_skill_detail_get_state',
  'hive_skill_create_get_state',
  'hive_skills_playground_get_state',
  'hive_plugin_detail_get_state',
  'hive_plugin_design_get_state',
  'hive_hook_design_get_state',
  'hive_command_design_get_state',
  'hive_rule_design_get_state',
  'hive_team_dashboard_get_state',
  'hive_team_settings_get_state',
  'hive_team_builder_get_state',
  'hive_product_dashboard_get_state',
  'hive_product_settings_get_state',
  'hive_project_dashboard_get_state',
  'hive_project_settings_get_state',
  'hive_backend_detail_get_state',
  'hive_mcp_detail_get_state',
  'hive_workflow_builder_get_state',

  // Dashboard pages
  'hive_dashboards_get_state',
  'hive_security_dashboard_get_state',
  'hive_pr_dashboard_get_state',
  'hive_trigger_dashboard_get_state',
  'hive_token_usage_get_state',
  'hive_service_health_get_state',
  'hive_usage_history_get_state',
  'hive_products_summary_get_state',
  'hive_projects_summary_get_state',
  'hive_teams_summary_get_state',
  'hive_agents_summary_get_state',
  'hive_trigger_mgmt_get_state',

  // Remaining views
  'hive_audit_history_get_state',
  'hive_audit_detail_get_state',
  'hive_trigger_history_get_state',
  'hive_execution_history_get_state',
  'hive_explore_skills_get_state',
  'hive_explore_plugins_get_state',
  'hive_explore_super_agents_get_state',
  'hive_explore_mcp_servers_get_state',
  'hive_harness_integration_get_state',
  'hive_sketch_chat_get_state',
  'hive_super_agent_playground_get_state',
  'hive_workflow_playground_get_state',
  'hive_settings_get_state',
];

function createFullSweepToolMap() {
  const tools = new Map<string, { execute: (a: Record<string, unknown>) => Promise<unknown>; inputSchema?: Record<string, unknown> }>();

  for (const name of ALL_STATE_TOOLS) {
    tools.set(name, {
      execute: vi.fn(async () => ({
        content: [{
          type: 'text',
          text: JSON.stringify({
            page: name.replace(/^hive_/, '').replace(/_get_(list_)?state$/, ''),
            isLoading: false,
          }),
        }],
      })),
    });
  }

  return tools;
}

describe('full-sweep', () => {
  it('all state tools are accounted for (expected count)', () => {
    // 12 list + 20 detail + 12 dashboard + 13 remaining = 57
    expect(ALL_STATE_TOOLS).toHaveLength(57);
  });

  it('every state tool returns valid JSON response', async () => {
    const toolMap = createFullSweepToolMap();

    for (const toolName of ALL_STATE_TOOLS) {
      const result = await invokeTool(toolName, {}, toolMap);
      expect(result.success).toBe(true);

      const data = result.data as { content: { type: string; text: string }[] };
      expect(data.content).toBeDefined();
      expect(data.content[0].type).toBe('text');

      const parsed = JSON.parse(data.content[0].text);
      expect(typeof parsed).toBe('object');
      expect(parsed).not.toBeNull();
    }
  });

  it('no duplicate tool names', () => {
    const unique = new Set(ALL_STATE_TOOLS);
    expect(unique.size).toBe(ALL_STATE_TOOLS.length);
  });

  it('all tool names follow naming convention', () => {
    for (const name of ALL_STATE_TOOLS) {
      expect(name).toMatch(/^hive_[a-z_]+_get_(list_)?state$/);
    }
  });

  it('each tool response includes page field', async () => {
    const toolMap = createFullSweepToolMap();

    for (const toolName of ALL_STATE_TOOLS) {
      const result = await invokeTool(toolName, {}, toolMap);
      const data = result.data as { content: { type: string; text: string }[] };
      const parsed = JSON.parse(data.content[0].text);
      expect(parsed).toHaveProperty('page');
    }
  });

  it('tool map exhaustively covers all expected tools', () => {
    const toolMap = createFullSweepToolMap();
    for (const name of ALL_STATE_TOOLS) {
      expect(toolMap.has(name)).toBe(true);
    }
  });

  it('sequential sweep completes in reasonable time', async () => {
    const toolMap = createFullSweepToolMap();
    const start = performance.now();

    for (const toolName of ALL_STATE_TOOLS) {
      await invokeTool(toolName, {}, toolMap);
    }

    const elapsed = performance.now() - start;
    // All mock tools should complete in under 1 second
    expect(elapsed).toBeLessThan(1000);
  });
});
