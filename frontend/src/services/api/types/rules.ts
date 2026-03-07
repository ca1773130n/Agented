/**
 * Rule types.
 */

export type RuleType = 'pre_check' | 'post_check' | 'validation';

export interface Rule {
  id: number;
  name: string;
  description?: string;
  rule_type: RuleType;
  condition?: string;
  action?: string;
  enabled: number;
  project_id?: string;
  source_path?: string;
  created_at?: string;
  updated_at?: string;
}
