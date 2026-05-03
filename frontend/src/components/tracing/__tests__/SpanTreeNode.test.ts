import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import SpanTreeNode from '../SpanTreeNode.vue';
import type { TraceSpan } from '../../../services/api/tracing';

function makeSpan(overrides: Partial<TraceSpan> = {}): TraceSpan {
  return {
    id: 'span-1',
    trace_id: 'trace-1',
    parent_span_id: null,
    name: 'Root',
    span_type: 'AGENT_RUN',
    status: 'running',
    started_at: '2026-05-03T00:00:00Z',
    finished_at: null,
    duration_ms: null,
    ...overrides,
  };
}

describe('SpanTreeNode', () => {
  it('renders the span name + status badge + span_type', () => {
    const span = makeSpan({ name: 'plan-step', status: 'completed', span_type: 'EXECUTION' });
    const wrapper = mount(SpanTreeNode, {
      props: { span, children: [] },
    });
    expect(wrapper.text()).toContain('plan-step');
    expect(wrapper.find('[data-testid="span-status"]').text()).toBe('completed');
    expect(wrapper.find('[data-testid="span-type"]').text()).toBe('EXECUTION');
  });

  it('renders child spans recursively', () => {
    const parent = makeSpan({ id: 'p', name: 'parent' });
    const child = makeSpan({ id: 'c', name: 'child', parent_span_id: 'p' });
    const wrapper = mount(SpanTreeNode, {
      props: { span: parent, children: [{ span: child, children: [] }] },
    });
    expect(wrapper.text()).toContain('parent');
    expect(wrapper.text()).toContain('child');
    // The child is rendered inside a nested SpanTreeNode.
    // VTU's findAllComponents searches `currentComponent.subTree`, so the
    // mounted root is not included — only the recursive descendant is.
    expect(wrapper.findAllComponents(SpanTreeNode).length).toBe(1);
  });

  it('expand/collapse toggles a body region', async () => {
    const wrapper = mount(SpanTreeNode, {
      props: { span: makeSpan(), children: [] },
    });
    expect(wrapper.find('[data-testid="span-body"]').exists()).toBe(false);
    await wrapper.find('[data-testid="span-toggle"]').trigger('click');
    expect(wrapper.find('[data-testid="span-body"]').exists()).toBe(true);
    await wrapper.find('[data-testid="span-toggle"]').trigger('click');
    expect(wrapper.find('[data-testid="span-body"]').exists()).toBe(false);
  });
});
