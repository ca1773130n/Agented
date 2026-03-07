/**
 * Chunk result types.
 */

export interface ChunkResult {
  chunk_index: number;
  chunk_content: string;
  bot_output: string;
  token_count: number;
}

export interface MergedChunkResults {
  total_chunks: number;
  unique_findings: string[];
  duplicate_count: number;
  merged_output: string;
  chunk_results: ChunkResult[];
}
