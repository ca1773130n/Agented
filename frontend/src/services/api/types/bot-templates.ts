/**
 * Bot Template types.
 */

export interface BotTemplate {
  id: string;
  slug: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  config_json: string;
  sort_order: number;
  source: string;
  is_published: number;
  created_at: string;
}

export interface BotTemplateDeployResponse {
  trigger_id: string;
  template_id: string;
  trigger_name: string;
  message: string;
}
