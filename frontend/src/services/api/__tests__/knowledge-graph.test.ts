import { describe, it, expect } from 'vitest';
import { knowledgeGraphApi } from '../knowledge-graph';
import type { KGEntity, KGRelation, KGSubgraph, KGStats } from '../knowledge-graph';

describe('knowledge-graph API', () => {
  it('exports knowledgeGraphApi with expected methods', () => {
    expect(knowledgeGraphApi).toBeDefined();
    expect(typeof knowledgeGraphApi.listEntities).toBe('function');
    expect(typeof knowledgeGraphApi.getEntity).toBe('function');
    expect(typeof knowledgeGraphApi.deleteEntity).toBe('function');
    expect(typeof knowledgeGraphApi.queryGraph).toBe('function');
    expect(typeof knowledgeGraphApi.searchEntities).toBe('function');
    expect(typeof knowledgeGraphApi.getStats).toBe('function');
  });

  it('has correct type shapes', () => {
    // Type-level test — verifies interfaces compile correctly
    const entity: KGEntity = {
      id: 'kge-test1234',
      agent_id: 'agent-test01',
      name: 'test-entity',
      entity_type: 'concept',
      properties: {},
      mention_count: 1,
      importance_score: 0.5,
      first_seen: '2026-01-01T00:00:00',
      last_seen: '2026-01-01T00:00:00',
    };
    expect(entity.name).toBe('test-entity');

    const relation: KGRelation = {
      id: 'kgr-test1234',
      agent_id: 'agent-test01',
      source_id: 'kge-src12345',
      target_id: 'kge-tgt12345',
      relation_type: 'uses',
      properties: {},
      confidence: 0.8,
      mention_count: 3,
    };
    expect(relation.relation_type).toBe('uses');

    const subgraph: KGSubgraph = {
      entities: [entity],
      relations: [relation],
    };
    expect(subgraph.entities).toHaveLength(1);

    const stats: KGStats = {
      entity_count: 10,
      relation_count: 5,
      top_entities: [entity],
      last_consolidation: null,
    };
    expect(stats.entity_count).toBe(10);
  });
});
