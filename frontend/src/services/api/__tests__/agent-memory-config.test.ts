import { describe, it, expect } from 'vitest';
import type { MemoryConfig, RecallResponse } from '../agent-memory';

describe('MemoryConfig type', () => {
  it('supports new feature toggle fields', () => {
    const config: MemoryConfig = {
      enabled: true,
      last_messages: 10,
      semantic_recall: { enabled: true, top_k: 5, message_range: 1 },
      working_memory: { enabled: true, scope: 'agent', template: '# Notes' },
      vector_search: { enabled: true },
      knowledge_graph: { enabled: true },
      crag_evaluation: { enabled: false },
      cross_thread: { enabled: false },
    };
    expect(config.vector_search?.enabled).toBe(true);
    expect(config.knowledge_graph?.enabled).toBe(true);
    expect(config.crag_evaluation?.enabled).toBe(false);
    expect(config.cross_thread?.enabled).toBe(false);
  });
});

describe('RecallResponse type', () => {
  it('supports CRAG evaluation fields', () => {
    const response: RecallResponse = {
      results: [],
      count: 0,
      query: 'test',
      search_mode: 'orchestrated',
      relevance_score: 0.85,
      retrieval_evaluation: 'correct',
      related_entities: [
        {
          id: 'kge-test1234',
          name: 'flask',
          entity_type: 'technology',
          importance_score: 0.8,
          mention_count: 15,
        },
      ],
      graph_context: 'flask --[uses]--> sqlite',
    };
    expect(response.retrieval_evaluation).toBe('correct');
    expect(response.related_entities).toHaveLength(1);
    expect(response.graph_context).toContain('flask');
  });
});
