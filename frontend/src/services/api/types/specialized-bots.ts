/**
 * Specialized Bot types.
 */

export interface SpecializedBotStatus {
  id: string;
  name: string;
  trigger_exists: boolean;
  skill_file_exists: boolean;
  trigger_source: string;
  enabled: boolean;
}

export interface SpecializedBotHealth {
  gh_authenticated: boolean;
  osv_scanner_available: boolean;
  search_index_count: number;
}

export interface ExecutionSearchResult {
  execution_id: string;
  trigger_id: string;
  trigger_name: string | null;
  started_at: string;
  status: string;
  prompt: string | null;
  stdout_match: string | null;
  stderr_match: string | null;
}

export interface ExecutionSearchResponse {
  results: ExecutionSearchResult[];
  total: number;
  query: string;
}

export interface ExecutionSearchStats {
  indexed_documents: number;
}
