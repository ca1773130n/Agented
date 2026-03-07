/**
 * Command types.
 */

export interface Command {
  id: number;
  name: string;
  description?: string;
  content?: string;
  arguments?: string;  // JSON array
  enabled: number;
  project_id?: string;
  source_path?: string;
  created_at?: string;
  updated_at?: string;
}
