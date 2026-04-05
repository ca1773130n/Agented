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

// Mock shiki
vi.mock('shiki/core', () => ({
  createHighlighterCoreSync: () => ({
    codeToHtml: (_code: string) => '<pre class="shiki"><code>highlighted</code></pre>',
    getLoadedLanguages: () => ['javascript', 'typescript', 'python'],
  }),
}));

vi.mock('shiki/engine/javascript', () => ({
  createJavaScriptRegExpEngine: () => ({}),
}));

vi.mock('shiki/themes/vitesse-dark.mjs', () => ({ default: {} }));

// Mock all shiki language imports
const langModules = [
  'javascript', 'typescript', 'python', 'bash', 'json', 'css', 'html',
  'sql', 'yaml', 'markdown', 'diff', 'go', 'rust', 'java', 'csharp',
  'ruby', 'php', 'shellscript', 'toml', 'xml', 'jsx', 'tsx', 'vue', 'dockerfile',
];
for (const lang of langModules) {
  vi.mock(`shiki/langs/${lang}.mjs`, () => ({ default: {} }));
}

import { renderMarkdown, highlightCodeBlocks, attachCodeCopyHandlers } from '../useMarkdown';

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
    it('processes un-highlighted code blocks', () => {
      const container = document.createElement('div');
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      pre.appendChild(code);
      container.appendChild(pre);

      highlightCodeBlocks(container);
      // Should mark as processed
      expect(code.getAttribute('data-shiki')).toBe('plain');
    });

    it('skips already-processed blocks', () => {
      const container = document.createElement('div');
      const pre = document.createElement('pre');
      const code = document.createElement('code');
      code.setAttribute('data-shiki', 'done');
      pre.appendChild(code);
      container.appendChild(pre);

      highlightCodeBlocks(container);
      expect(code.getAttribute('data-shiki')).toBe('done');
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
