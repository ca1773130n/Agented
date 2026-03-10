import { describe, it, expect } from 'vitest';
import { ref } from 'vue';
import type { Node, Edge, Connection } from '@vue-flow/core';
import { useTopologyValidation } from '../useTopologyValidation';

function makeNode(id: string, type = 'agent'): Node {
  return { id, type, position: { x: 0, y: 0 }, data: {} } as Node;
}

function makeEdge(source: string, target: string, label?: string): Edge {
  return { id: `${source}-${target}`, source, target, label } as Edge;
}

describe('useTopologyValidation', () => {
  describe('isValidConnection', () => {
    it('rejects self-connections', () => {
      const nodes = ref([makeNode('a')]);
      const edges = ref<Edge[]>([]);
      const { isValidConnection } = useTopologyValidation(nodes, edges);

      expect(isValidConnection({ source: 'a', target: 'a' } as Connection)).toBe(false);
    });

    it('rejects duplicate edges', () => {
      const nodes = ref([makeNode('a'), makeNode('b')]);
      const edges = ref([makeEdge('a', 'b')]);
      const { isValidConnection } = useTopologyValidation(nodes, edges);

      expect(isValidConnection({ source: 'a', target: 'b' } as Connection)).toBe(false);
    });

    it('accepts valid agent-to-agent connections', () => {
      const nodes = ref([makeNode('a'), makeNode('b')]);
      const edges = ref<Edge[]>([]);
      const { isValidConnection } = useTopologyValidation(nodes, edges);

      expect(isValidConnection({ source: 'a', target: 'b' } as Connection)).toBe(true);
    });

    it('rejects connections involving non-agent node types', () => {
      const nodes = ref([makeNode('a', 'agent'), makeNode('b', 'input')]);
      const edges = ref<Edge[]>([]);
      const { isValidConnection } = useTopologyValidation(nodes, edges);

      expect(isValidConnection({ source: 'a', target: 'b' } as Connection)).toBe(false);
    });

    it('accepts super_agent node types', () => {
      const nodes = ref([makeNode('a', 'super_agent'), makeNode('b', 'agent')]);
      const edges = ref<Edge[]>([]);
      const { isValidConnection } = useTopologyValidation(nodes, edges);

      expect(isValidConnection({ source: 'a', target: 'b' } as Connection)).toBe(true);
    });

    it('enforces hierarchical tier constraints', () => {
      const nodes = ref([makeNode('a'), makeNode('b')]);
      const edges = ref<Edge[]>([]);
      const topology = ref<string | null>('hierarchical');
      const getTier = (id: string) => (id === 'a' ? 'member' : 'member');

      const { isValidConnection } = useTopologyValidation(nodes, edges, topology, getTier);

      // Member -> member should be rejected (targetRank not > sourceRank)
      expect(isValidConnection({ source: 'a', target: 'b' } as Connection)).toBe(false);
    });

    it('allows member to senior in hierarchical topology', () => {
      const nodes = ref([makeNode('a'), makeNode('b')]);
      const edges = ref<Edge[]>([]);
      const topology = ref<string | null>('hierarchical');
      const getTier = (id: string) => (id === 'a' ? 'member' : 'senior');

      const { isValidConnection } = useTopologyValidation(nodes, edges, topology, getTier);
      expect(isValidConnection({ source: 'a', target: 'b' } as Connection)).toBe(true);
    });
  });

  describe('inferredTopology', () => {
    it('returns null for no nodes', () => {
      const nodes = ref<Node[]>([]);
      const edges = ref<Edge[]>([]);
      const { inferredTopology } = useTopologyValidation(nodes, edges);

      expect(inferredTopology.value).toBeNull();
    });

    it('infers parallel when multiple nodes and no edges', () => {
      const nodes = ref([makeNode('a'), makeNode('b'), makeNode('c')]);
      const edges = ref<Edge[]>([]);
      const { inferredTopology } = useTopologyValidation(nodes, edges);

      expect(inferredTopology.value).toBe('parallel');
    });

    it('infers generator_critic for 2 nodes with bidirectional edges', () => {
      const nodes = ref([makeNode('a'), makeNode('b')]);
      const edges = ref([makeEdge('a', 'b'), makeEdge('b', 'a')]);
      const { inferredTopology } = useTopologyValidation(nodes, edges);

      expect(inferredTopology.value).toBe('generator_critic');
    });

    it('infers sequential for a 2-node chain (not matching hierarchical min-3 requirement)', () => {
      // With exactly 2 nodes in a chain (no bidirectional), hierarchical requires >= 3 nodes,
      // coordinator requires >= 3 nodes, so it falls through to sequential.
      const nodes = ref([makeNode('a'), makeNode('b')]);
      const edges = ref([makeEdge('a', 'b')]);
      const { inferredTopology } = useTopologyValidation(nodes, edges);

      expect(inferredTopology.value).toBe('sequential');
    });

    it('infers coordinator for hub-spoke pattern', () => {
      const nodes = ref([makeNode('hub'), makeNode('w1'), makeNode('w2')]);
      const edges = ref([makeEdge('hub', 'w1'), makeEdge('hub', 'w2')]);
      const { inferredTopology } = useTopologyValidation(nodes, edges);

      expect(inferredTopology.value).toBe('coordinator');
    });

    it('infers hierarchical for tree-shaped DAG', () => {
      // The root fans out to two branches, each with a leaf, so no single
      // node connects to ALL others (avoiding coordinator match).
      const nodes = ref([
        makeNode('root'), makeNode('left'), makeNode('right'),
        makeNode('ll'), makeNode('rl'),
      ]);
      const edges = ref([
        makeEdge('root', 'left'), makeEdge('root', 'right'),
        makeEdge('left', 'll'), makeEdge('right', 'rl'),
      ]);
      const { inferredTopology } = useTopologyValidation(nodes, edges);

      expect(inferredTopology.value).toBe('hierarchical');
    });
  });

  describe('warnings', () => {
    it('returns empty array for fewer than 2 nodes', () => {
      const nodes = ref([makeNode('a')]);
      const edges = ref<Edge[]>([]);
      const { warnings } = useTopologyValidation(nodes, edges);

      expect(warnings.value).toEqual([]);
    });

    it('warns about disconnected agents when some are connected', () => {
      const nodes = ref([makeNode('a'), makeNode('b'), makeNode('c')]);
      const edges = ref([makeEdge('a', 'b')]);
      const { warnings } = useTopologyValidation(nodes, edges);

      expect(warnings.value.some((w) => w.includes('disconnected'))).toBe(true);
    });

    it('warns about hub-spoke with no return edges', () => {
      const nodes = ref([makeNode('hub'), makeNode('w1'), makeNode('w2')]);
      const edges = ref([makeEdge('hub', 'w1'), makeEdge('hub', 'w2')]);
      const { warnings } = useTopologyValidation(nodes, edges);

      expect(warnings.value.some((w) => w.includes('Coordinator pattern'))).toBe(true);
    });
  });
});
