/**
 * Hook types.
 */

export type HookEvent =
  | 'PreToolUse'
  | 'PostToolUse'
  | 'Stop'
  | 'SubagentStop'
  | 'SessionStart'
  | 'SessionEnd'
  | 'UserPromptSubmit'
  | 'PreCompact'
  | 'Notification';

export interface Hook {
  id: number;
  name: string;
  event: HookEvent;
  description?: string;
  content?: string;
  enabled: number;
  project_id?: string;
  source_path?: string;
  created_at?: string;
  updated_at?: string;
}
