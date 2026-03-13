/**
 * Prompt Snippet and Prompt History types.
 */

export interface PromptSnippet {
  id: string;
  name: string;
  content: string;
  description: string;
  is_global: number;
  created_at: string;
  updated_at: string;
}

export interface CreateSnippetRequest {
  name: string;
  content: string;
  description?: string;
}

export interface UpdateSnippetRequest {
  name?: string;
  content?: string;
  description?: string;
}

// Prompt History types
export interface PromptHistoryEntry {
  id: number;
  trigger_id: string;
  old_template: string;
  new_template: string;
  author: string;
  diff_text: string;
  changed_at: string;
}

// Full Preview types
export interface PreviewPromptFullResponse {
  rendered_prompt: string;
  cli_command: string;
  cli_command_parts: string[];
  backend_type: string;
  model: string;
  trigger_name: string;
  unresolved_placeholders: string[];
  unresolved_snippets: string[];
}

// Dry Run response (from POST /admin/triggers/<id>/dry-run)
export interface DryRunResponse {
  rendered_prompt: string;
  cli_command: string;
  backend_type: string;
  model: string;
  estimated_tokens: {
    estimated_input_tokens: number;
    estimated_output_tokens: number;
    estimated_cost_usd: number;
    model: string;
    confidence: string;
  };
  trigger_id: string;
  trigger_name: string;
}
