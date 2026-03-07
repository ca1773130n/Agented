/**
 * User skills, harness config, and file tree types.
 */

export interface UserSkill {
  id: number;
  skill_name: string;
  skill_path: string;
  description?: string;
  enabled: number;
  selected_for_harness: number;
  metadata?: string;
  created_at?: string;
  updated_at?: string;
}

export interface HarnessConfig {
  skills: UserSkill[];
  config_json: string;
}

// File tree node for playground browser
export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileNode[];
}

// Skills.sh types
export interface SkillsShResult {
  name: string;
  description?: string;
  source?: string;
  installs?: number;
  detail_url?: string;
  install_cmd?: string;
  installed?: boolean;
}

export interface LoadFromMarketplaceResponse {
  message: string;
  imported_skills: string[];
  plugin_name: string;
  marketplace: string;
}

export interface DeployToMarketplaceResponse {
  message: string;
  plugin_name: string;
  marketplace: string;
  marketplace_url: string;
  config: Record<string, unknown>;
  config_json: string;
  instructions: string[];
}
