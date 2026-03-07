/**
 * MCP Server types.
 */

export interface McpServer {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  server_type: string;
  command: string | null;
  args: string | null;
  env_json: string | null;
  url: string | null;
  headers_json: string | null;
  timeout_ms: number;
  is_preset: number;
  icon: string | null;
  documentation_url: string | null;
  npm_package: string | null;
  enabled: number;
  created_at: string | null;
  updated_at: string | null;
  category: string;
}

export interface ProjectMcpServerDetail extends McpServer {
  project_id: string;
  mcp_server_id: string;
  assignment_enabled: number;
  env_overrides_json: string | null;
  config_override: string | null;
}

export interface McpSyncResult {
  written?: string;
  servers?: number;
  backup?: string | null;
  diff?: string;
  would_write?: string;
  servers_count?: number;
  error?: string;
}
