/**
 * Chunked execution API module.
 *
 * Provides functions for triggering chunked bot executions, checking status,
 * and retrieving merged/deduplicated results from multi-chunk processing.
 */
import { apiFetch } from './client';
import type { MergedChunkResults } from './types';

export const chunkApi = {
  /** Trigger a chunked execution for a bot. */
  runChunked: (botId: string, data: { content: string; max_chunk_chars?: number }) =>
    apiFetch<{
      chunked_execution_id: string;
      bot_id: string;
      total_chunks: number;
      status: string;
    }>(
      `/admin/bots/${botId}/run-chunked`,
      { method: 'POST', body: JSON.stringify(data) }
    ),

  /** Get the status of a chunked execution. */
  getStatus: (chunkedExecutionId: string) =>
    apiFetch<{
      id: string;
      bot_id: string;
      total_chunks: number;
      completed_chunks: number;
      status: string;
    }>(
      `/admin/chunked-executions/${chunkedExecutionId}`
    ),

  /** Get merged/deduplicated results from a chunked execution. */
  getResults: (chunkedExecutionId: string) =>
    apiFetch<MergedChunkResults>(
      `/admin/chunked-executions/${chunkedExecutionId}/results`
    ),
};
