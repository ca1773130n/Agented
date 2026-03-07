/**
 * Plugin, plugin export/import, and sync types.
 */

export interface PluginComponent {
  id: number;
  plugin_id: string;
  name: string;
  type: string;
  content?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Plugin {
  id: string;
  name: string;
  description?: string;
  version: string;
  status: string;
  author?: string;
  component_count: number;
  created_at?: string;
  updated_at?: string;
  components?: PluginComponent[];
}

// Plugin Export/Import types
export interface PluginExportRequest {
  team_id: string;
  export_format: 'claude' | 'agented';
  output_dir?: string;
  plugin_id?: string;
}

export interface PluginExportResponse {
  export_path: string;
  plugin_name: string;
  format: string;
  agents: number;
  skills: number;
  commands: number;
  hooks: number;
  rules: number;
}

export interface PluginImportRequest {
  source_path: string;
  plugin_name?: string;
}

export interface PluginImportFromMarketplaceRequest {
  marketplace_id: string;
  remote_plugin_name: string;
}

export interface PluginImportResponse {
  plugin_id: string;
  plugin_name: string;
  agents_imported: number;
  skills_imported: number;
  commands_imported: number;
  hooks_imported: number;
  rules_imported: number;
}

export interface PluginDeployRequest {
  plugin_id: string;
  marketplace_id: string;
  version?: string;
}

export interface PluginDeployResponse {
  message: string;
  marketplace_url: string;
  plugin_name: string;
}

export interface SyncStatus {
  plugin_id: string;
  status: string;
  entities_synced: number;
  last_synced_at: string | null;
  watching: boolean;
}

export interface PluginExportRecord {
  id: number;
  plugin_id: string;
  team_id: string | null;
  export_format: string;
  export_path: string | null;
  status: string;
  version: string;
  last_exported_at: string | null;
}
