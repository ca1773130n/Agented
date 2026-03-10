import { describe, it, expect, vi } from 'vitest';

// Mock marked
vi.mock('marked', () => {
  class MockMarked {
    constructor() {}
    parse(content: string) {
      return `<p>${content}</p>`;
    }
  }
  return { Marked: MockMarked };
});

// Mock DOMPurify
vi.mock('dompurify', () => ({
  default: {
    sanitize: (html: string) => html,
  },
}));

// Mock highlight.js
vi.mock('highlight.js/lib/core', () => ({
  default: {
    registerLanguage: vi.fn(),
    getLanguage: vi.fn(),
    highlight: vi.fn().mockReturnValue({ value: 'highlighted' }),
    highlightAuto: vi.fn().mockReturnValue({ value: 'auto-highlighted' }),
    highlightElement: vi.fn(),
  },
}));

// Mock all language imports individually (vi.mock is hoisted, no loops allowed)
vi.mock('highlight.js/lib/languages/javascript', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/typescript', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/python', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/bash', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/json', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/css', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/xml', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/sql', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/yaml', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/markdown', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/diff', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/go', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/rust', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/java', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/csharp', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/ruby', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/php', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/shell', () => ({ default: vi.fn() }));
vi.mock('highlight.js/lib/languages/plaintext', () => ({ default: vi.fn() }));
vi.mock('highlight.js/styles/github-dark-dimmed.min.css', () => ({}));

import { renderMarkdown, highlightCodeBlocks, attachCodeCopyHandlers } from '../useMarkdown';
import hljs from 'highlight.js/lib/core';

describe('useMarkdown', () => {
  describe('renderMarkdown', () => {
    it('returns sanitized HTML from markdown content', () => {
      const result = renderMarkdown('Hello world');
      expect(result).toContain('Hello world');
    });

    it('returns a string for any input', () => {
      const result = renderMarkdown('# Heading\n\nParagraph');
      expect(typeof result).toBe('string');
    });
  });

  describe('highlightCodeBlocks', () => {
    it('calls highlightElement on un-highlighted code blocks', () => {
      const container = document.createElement('div');
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      pre.appendChild(code);
      container.appendChild(pre);

      highlightCodeBlocks(container);
      expect(hljs.highlightElement).toHaveBeenCalledWith(code);
    });

    it('skips already-highlighted blocks (with .hljs class)', () => {
      const container = document.createElement('div');
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      code.classList.add('hljs');
      pre.appendChild(code);
      container.appendChild(pre);

      vi.mocked(hljs.highlightElement).mockClear();
      highlightCodeBlocks(container);
      expect(hljs.highlightElement).not.toHaveBeenCalled();
    });
  });

  describe('attachCodeCopyHandlers', () => {
    it('attaches click handler to copy buttons', () => {
      const container = document.createElement('div');
      const wrapper = document.createElement('div');
      wrapper.className = 'code-block-wrapper';
      const header = document.createElement('div');
      header.className = 'code-block-header';
      const btn = document.createElement('button');
      btn.setAttribute('data-copy-code', 'true');
      btn.textContent = 'Copy';
      header.appendChild(btn);
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      code.textContent = 'some code';
      pre.appendChild(code);
      wrapper.appendChild(header);
      wrapper.appendChild(pre);
      container.appendChild(wrapper);

      attachCodeCopyHandlers(container);
      expect(btn.dataset.copyHandlerAttached).toBe('true');
    });

    it('does not attach duplicate handlers', () => {
      const container = document.createElement('div');
      const wrapper = document.createElement('div');
      wrapper.className = 'code-block-wrapper';
      const header = document.createElement('div');
      header.className = 'code-block-header';
      const btn = document.createElement('button');
      btn.setAttribute('data-copy-code', 'true');
      btn.textContent = 'Copy';
      header.appendChild(btn);
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      code.textContent = 'code';
      pre.appendChild(code);
      wrapper.appendChild(header);
      wrapper.appendChild(pre);
      container.appendChild(wrapper);

      attachCodeCopyHandlers(container);
      attachCodeCopyHandlers(container);

      expect(btn.dataset.copyHandlerAttached).toBe('true');
    });
  });
});
