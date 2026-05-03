import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import MessageList from '../MessageList.vue';

const sampleMessages = [
  { id: 'm1', thread_id: 't1', role: 'user', content: 'Hello, plan a trip', created_at: '2026-05-04T10:00:00Z' },
  { id: 'm2', thread_id: 't1', role: 'assistant', content: 'Sure, I will plan a trip to…', created_at: '2026-05-04T10:00:01Z' },
  { id: 'm3', thread_id: 't1', role: 'tool', content: 'web_search results: …', created_at: '2026-05-04T10:00:02Z' },
];

describe('MessageList', () => {
  it('renders one row per message (each containing a ChatBubble)', () => {
    const wrapper = mount(MessageList, {
      props: { messages: sampleMessages },
    });
    expect(wrapper.findAll('[data-testid="message-row"]')).toHaveLength(3);
  });

  it('passes role and content through to each row', () => {
    const wrapper = mount(MessageList, {
      props: { messages: sampleMessages },
    });
    const text = wrapper.text();
    expect(text).toContain('Hello, plan a trip');
    expect(text).toContain('Sure, I will plan');
    expect(text).toContain('web_search results');
  });

  it('shows empty state when no messages', () => {
    const wrapper = mount(MessageList, { props: { messages: [] } });
    expect(wrapper.find('[data-testid="message-list-empty"]').exists()).toBe(true);
  });
});
