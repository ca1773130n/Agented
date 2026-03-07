import { describe, it, expect } from 'vitest';
import { useWorkflowValidation } from '../useWorkflowValidation';
import type { Node, Edge, Connection } from '@vue-flow/core';

function makeNode(id: string, type: string, config?: Record<string, unknown>): Node {
  return {
    id,
    type,
    position: { x: 0, y: 0 },
    data: { label: id, config },
  };
}

function makeEdge(source: string, target: string): Edge {
  return { id: `${source}-${target}`, source, target };
}

describe('useWorkflowValidation', () => {
  const { validateGraph, isValidConnection } = useWorkflowValidation();

  describe('validateGraph', () => {
    it('returns no errors for empty graph', () => {
      expect(validateGraph([], [])).toEqual([]);
    });

    it('returns error when no trigger node', () => {
      const nodes = [makeNode('n1', 'command', { command: 'echo hi' })];
      const results = validateGraph(nodes, []);
      expect(results.some(r => r.level === 'error' && r.message.includes('Trigger'))).toBe(true);
    });

    it('returns no trigger error when trigger exists', () => {
      const nodes = [makeNode('t1', 'trigger')];
      const results = validateGraph(nodes, []);
      expect(results.some(r => r.message.includes('must have at least one Trigger'))).toBe(false);
    });

    it('warns about multiple triggers', () => {
      const nodes = [makeNode('t1', 'trigger'), makeNode('t2', 'trigger')];
      const results = validateGraph(nodes, []);
      expect(results.some(r => r.level === 'warning' && r.message.includes('Multiple Trigger'))).toBe(true);
    });

    it('warns about orphaned non-trigger nodes', () => {
      const nodes = [
        makeNode('t1', 'trigger'),
        makeNode('n1', 'command', { command: 'echo' }),
        makeNode('n2', 'script', { script: 'echo' }),
      ];
      const edges = [makeEdge('t1', 'n1')];
      const results = validateGraph(nodes, edges);
      expect(results.some(r => r.level === 'warning' && r.message.includes('orphaned'))).toBe(true);
    });

    it('detects simple cycle (A->B->A)', () => {
      const nodes = [makeNode('a', 'command'), makeNode('b', 'command')];
      const edges = [makeEdge('a', 'b'), makeEdge('b', 'a')];
      const results = validateGraph(nodes, edges);
      expect(results.some(r => r.level === 'error' && r.message.includes('Cycle'))).toBe(true);
    });

    it('detects three-node cycle (A->B->C->A)', () => {
      const nodes = [makeNode('a', 'command'), makeNode('b', 'command'), makeNode('c', 'command')];
      const edges = [makeEdge('a', 'b'), makeEdge('b', 'c'), makeEdge('c', 'a')];
      const results = validateGraph(nodes, edges);
      const cycleResult = results.find(r => r.message.includes('Cycle'));
      expect(cycleResult).toBeDefined();
      expect(cycleResult!.nodeIds).toBeDefined();
      expect(cycleResult!.nodeIds!.length).toBeGreaterThanOrEqual(3);
    });

    it('accepts valid DAG with no cycles', () => {
      const nodes = [
        makeNode('t1', 'trigger'),
        makeNode('n1', 'command', { command: 'echo' }),
        makeNode('n2', 'script', { script: 'echo' }),
      ];
      const edges = [makeEdge('t1', 'n1'), makeEdge('n1', 'n2')];
      const results = validateGraph(nodes, edges);
      expect(results.some(r => r.message.includes('Cycle'))).toBe(false);
    });

    it('warns about empty command config', () => {
      const nodes = [makeNode('n1', 'command', { command: '' })];
      const results = validateGraph(nodes, []);
      expect(results.some(r => r.message.includes('empty command'))).toBe(true);
    });

    it('warns about empty script config', () => {
      const nodes = [makeNode('n1', 'script', { script: '  ' })];
      const results = validateGraph(nodes, []);
      expect(results.some(r => r.message.includes('empty script'))).toBe(true);
    });

    it('warns about conditional without condition_type', () => {
      const nodes = [makeNode('n1', 'conditional', {})];
      const results = validateGraph(nodes, []);
      expect(results.some(r => r.message.includes('no condition type'))).toBe(true);
    });

    it('warns about invalid approval gate timeout', () => {
      const nodes = [makeNode('n1', 'approval_gate', { timeout_seconds: -1 })];
      const results = validateGraph(nodes, []);
      expect(results.some(r => r.message.includes('invalid timeout'))).toBe(true);
    });

    it('errors when approval gate has no input', () => {
      const nodes = [makeNode('ag1', 'approval_gate', {})];
      const results = validateGraph(nodes, []);
      expect(results.some(r => r.level === 'error' && r.message.includes('Approval gate'))).toBe(true);
    });

    it('detects port type mismatch', () => {
      // transform outputs 'json', command expects 'text'
      const nodes = [makeNode('n1', 'transform'), makeNode('n2', 'command')];
      const edges = [makeEdge('n1', 'n2')];
      const results = validateGraph(nodes, edges);
      expect(results.some(r => r.message.includes('Port type mismatch'))).toBe(true);
    });

    it('allows compatible port types', () => {
      // skill outputs 'text', agent expects 'text'
      const nodes = [makeNode('n1', 'skill'), makeNode('n2', 'agent')];
      const edges = [makeEdge('n1', 'n2')];
      const results = validateGraph(nodes, edges);
      expect(results.some(r => r.message.includes('Port type mismatch'))).toBe(false);
    });
  });

  describe('isValidConnection', () => {
    it('rejects self-connection', () => {
      const nodes = [makeNode('n1', 'command')];
      const conn: Connection = { source: 'n1', target: 'n1', sourceHandle: null, targetHandle: null };
      expect(isValidConnection(conn, nodes, [])).toBe(false);
    });

    it('rejects duplicate edges', () => {
      const nodes = [makeNode('n1', 'command'), makeNode('n2', 'command')];
      const edges = [makeEdge('n1', 'n2')];
      const conn: Connection = { source: 'n1', target: 'n2', sourceHandle: null, targetHandle: null };
      expect(isValidConnection(conn, nodes, edges)).toBe(false);
    });

    it('rejects connection to trigger node', () => {
      const nodes = [makeNode('n1', 'command'), makeNode('t1', 'trigger')];
      const conn: Connection = { source: 'n1', target: 't1', sourceHandle: null, targetHandle: null };
      expect(isValidConnection(conn, nodes, [])).toBe(false);
    });

    it('allows valid connection', () => {
      const nodes = [makeNode('t1', 'trigger'), makeNode('n1', 'command')];
      const conn: Connection = { source: 't1', target: 'n1', sourceHandle: null, targetHandle: null };
      expect(isValidConnection(conn, nodes, [])).toBe(true);
    });

    it('rejects incompatible port types', () => {
      // transform outputs 'json', command expects 'text'
      const nodes = [makeNode('n1', 'transform'), makeNode('n2', 'command')];
      const conn: Connection = { source: 'n1', target: 'n2', sourceHandle: null, targetHandle: null };
      expect(isValidConnection(conn, nodes, [])).toBe(false);
    });
  });
});
