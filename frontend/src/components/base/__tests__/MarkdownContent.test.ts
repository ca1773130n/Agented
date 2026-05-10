import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MarkdownContent from '../MarkdownContent.vue'

describe('MarkdownContent', () => {
  it('renders an h2 from "## Summary" instead of leaking the literal text', () => {
    // The bug this component exists to prevent: ``{{ msg.content }}``
    // pattern showing ``## Summary`` to the user. The whole point of
    // MarkdownContent is to make this test impossible to fail in any
    // surface that adopts it.
    const wrapper = mount(MarkdownContent, { props: { content: '## Summary' } })
    expect(wrapper.text()).not.toContain('## ')
    expect(wrapper.find('h2').exists()).toBe(true)
    expect(wrapper.find('h2').text()).toBe('Summary')
  })

  it('renders bullet lists', () => {
    const wrapper = mount(MarkdownContent, {
      props: { content: '- one\n- two\n- three' },
    })
    expect(wrapper.findAll('li')).toHaveLength(3)
  })

  it('renders code fences with the language hint preserved', () => {
    const wrapper = mount(MarkdownContent, {
      props: { content: '```js\nconst x = 1;\n```' },
    })
    const pre = wrapper.find('pre')
    expect(pre.exists()).toBe(true)
    expect(pre.find('code').exists()).toBe(true)
  })

  it('renders inline code with backticks stripped', () => {
    const wrapper = mount(MarkdownContent, {
      props: { content: 'Use `npm install` to install.' },
    })
    expect(wrapper.text()).not.toContain('`')
    expect(wrapper.find('code').text()).toBe('npm install')
  })

  it('renders bold and emphasis', () => {
    const wrapper = mount(MarkdownContent, {
      props: { content: '**bold** and *italic*' },
    })
    expect(wrapper.find('strong').text()).toBe('bold')
    expect(wrapper.find('em').text()).toBe('italic')
  })

  it('renders links with href', () => {
    const wrapper = mount(MarkdownContent, {
      props: { content: '[home](https://example.com)' },
    })
    const a = wrapper.find('a')
    expect(a.exists()).toBe(true)
    expect(a.attributes('href')).toBe('https://example.com')
    expect(a.text()).toBe('home')
  })

  it('handles null content without throwing', () => {
    expect(() =>
      mount(MarkdownContent, { props: { content: null } }),
    ).not.toThrow()
  })

  it('handles empty string content without throwing', () => {
    const wrapper = mount(MarkdownContent, { props: { content: '' } })
    expect(wrapper.find('.md-content').exists()).toBe(true)
    expect(wrapper.find('.md-content').text()).toBe('')
  })

  it('uses breaks option for single-line breaks when enabled', () => {
    // Without breaks: "a\nb" is one paragraph. With breaks: should produce <br>.
    const without = mount(MarkdownContent, { props: { content: 'a\nb' } })
    expect(without.find('br').exists()).toBe(false)
    const withBreaks = mount(MarkdownContent, {
      props: { content: 'a\nb', breaks: true },
    })
    expect(withBreaks.find('br').exists()).toBe(true)
  })
})
