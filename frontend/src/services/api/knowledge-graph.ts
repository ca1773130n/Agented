/**
 * Knowledge graph API module.
 * Provides entity and relation management for agent knowledge graphs.
 */
import { apiFetch } from './client';

export interface KGEntity {
  id: string;
  agent_id: string;
  name: string;
  entity_type: string;
  properties: Record<string, unknown>;
  mention_count: number;
  importance_score: number;
  first_seen: string;
  last_seen: string;
  relations?: KGRelation[];
}

export interface KGRelation {
  id: string;
  agent_id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  properties: Record<string, unknown>;
  confidence: number;
  mention_count: number;
  source_name?: string;
  target_name?: string;
}

export interface KGSubgraph {
  entities: KGEntity[];
  relations: KGRelation[];
}

export interface KGStats {
  entity_count: number;
  relation_count: number;
  top_entities: KGEntity[];
  last_consolidation: string | null;
}

export const knowledgeGraphApi = {
  listEntities: (agentId: string) =>
    apiFetch<{ entities: KGEntity[]; total: number }>(
      `/admin/agents/${agentId}/knowledge/entities`
    ),

  getEntity: (agentId: string, entityId: string) =>
    apiFetch<KGEntity>(`/admin/agents/${agentId}/knowledge/entities/${entityId}`),

  deleteEntity: (agentId: string, entityId: string) =>
    apiFetch<{ message: string }>(
      `/admin/agents/${agentId}/knowledge/entities/${entityId}`,
      { method: 'DELETE' }
    ),

  queryGraph: (agentId: string, seed: string, hops = 1) => {
    const params = new URLSearchParams({ seed, hops: String(hops) });
    return apiFetch<KGSubgraph>(`/admin/agents/${agentId}/knowledge/graph?${params}`);
  },

  searchEntities: (agentId: string, query: string) => {
    const params = new URLSearchParams({ q: query });
    return apiFetch<{ entities: KGEntity[]; total: number }>(
      `/admin/agents/${agentId}/knowledge/search?${params}`
    );
  },

  getStats: (agentId: string) =>
    apiFetch<KGStats>(`/admin/agents/${agentId}/knowledge/stats`),

  triggerConsolidation: (agentId: string) =>
    apiFetch<{ consolidated: number; details: Array<Record<string, unknown>> }>(
      `/admin/agents/${agentId}/knowledge/consolidate`,
      { method: 'POST' }
    ),
};
