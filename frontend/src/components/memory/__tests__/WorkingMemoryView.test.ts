// @vitest-environment jsdom
// Renders markdown via MarkdownContent (DOMPurify), which needs a real DOM —
// happy-dom breaks sanitization. Run under jsdom.
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import WorkingMemoryView from '../WorkingMemoryView.vue';

describe('WorkingMemoryView', () => {
  it('renders markdown content', () => {
    const wrapper = mount(WorkingMemoryView, {
      props: { content: '# Notes\n\n- fact A\n- fact B' },
    });
    const body = wrapper.find('[data-testid="working-memory-body"]');
    expect(body.exists()).toBe(true);
    // renderMarkdown turns # Notes into <h1>Notes</h1>
    expect(body.html()).toContain('<h1');
    expect(body.text()).toContain('fact A');
  });

  it('shows empty state when content is empty string', () => {
    const wrapper = mount(WorkingMemoryView, { props: { content: '' } });
    expect(wrapper.find('[data-testid="working-memory-empty"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="working-memory-body"]').exists()).toBe(false);
  });

  it('shows empty state when content is null', () => {
    const wrapper = mount(WorkingMemoryView, { props: { content: null } });
    expect(wrapper.find('[data-testid="working-memory-empty"]').exists()).toBe(true);
  });

  it('shows loading state when loading is true', () => {
    const wrapper = mount(WorkingMemoryView, { props: { content: null, loading: true } });
    expect(wrapper.find('[data-testid="working-memory-loading"]').exists()).toBe(true);
  });

  it('shows error state when error is set', () => {
    const wrapper = mount(WorkingMemoryView, { props: { content: null, error: 'oops' } });
    expect(wrapper.find('[data-testid="working-memory-error"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('oops');
  });
});
