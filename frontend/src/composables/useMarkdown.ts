import { Marked, type Tokens } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/core';
import 'highlight.js/styles/github-dark-dimmed.min.css';

// Register only common languages to keep bundle small
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import python from 'highlight.js/lib/languages/python';
import bash from 'highlight.js/lib/languages/bash';
import json from 'highlight.js/lib/languages/json';
import cssLang from 'highlight.js/lib/languages/css';
import xml from 'highlight.js/lib/languages/xml';
import sql from 'highlight.js/lib/languages/sql';
import yaml from 'highlight.js/lib/languages/yaml';
import markdownLang from 'highlight.js/lib/languages/markdown';
import diff from 'highlight.js/lib/languages/diff';
import go from 'highlight.js/lib/languages/go';
import rust from 'highlight.js/lib/languages/rust';
import java from 'highlight.js/lib/languages/java';
import csharp from 'highlight.js/lib/languages/csharp';
import ruby from 'highlight.js/lib/languages/ruby';
import php from 'highlight.js/lib/languages/php';
import shell from 'highlight.js/lib/languages/shell';
import plaintext from 'highlight.js/lib/languages/plaintext';

hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('js', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('ts', typescript);
hljs.registerLanguage('python', python);
hljs.registerLanguage('py', python);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('sh', bash);
hljs.registerLanguage('zsh', bash);
hljs.registerLanguage('json', json);
hljs.registerLanguage('css', cssLang);
hljs.registerLanguage('html', xml);
hljs.registerLanguage('xml', xml);
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('yml', yaml);
hljs.registerLanguage('markdown', markdownLang);
hljs.registerLanguage('md', markdownLang);
hljs.registerLanguage('diff', diff);
hljs.registerLanguage('go', go);
hljs.registerLanguage('rust', rust);
hljs.registerLanguage('rs', rust);
hljs.registerLanguage('java', java);
hljs.registerLanguage('csharp', csharp);
hljs.registerLanguage('cs', csharp);
hljs.registerLanguage('ruby', ruby);
hljs.registerLanguage('rb', ruby);
hljs.registerLanguage('php', php);
hljs.registerLanguage('shell', shell);
hljs.registerLanguage('plaintext', plaintext);
hljs.registerLanguage('text', plaintext);

const marked = new Marked({
  breaks: true,
  gfm: true,
  renderer: {
    code(token: Tokens.Code) {
      const lang = token.lang;
      const text = token.text;
      const language = lang && hljs.getLanguage(lang) ? lang : null;
      const highlighted = language
        ? hljs.highlight(text, { language }).value
        : hljs.highlightAuto(text).value;
      const displayLang = lang || 'code';
      return `<div class="code-block-wrapper"><div class="code-block-header"><span class="code-lang">${displayLang}</span><button class="code-copy-btn" data-copy-code="true">Copy</button></div><pre><code class="hljs${language ? ` language-${language}` : ''}">${highlighted}</code></pre></div>`;
    },
    codespan(token: Tokens.Codespan) {
      return `<code class="inline-code">${token.text}</code>`;
    },
    link(token: Tokens.Link) {
      const href = token.href;
      const text = this.parser.parseInline(token.tokens);
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`;
    },
  },
});

export function renderMarkdown(content: string): string {
  const raw = marked.parse(content) as string;
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['class', 'target', 'rel', 'data-copy-code'],
  });
}

/**
 * Post-process a DOM container to apply highlight.js to any un-highlighted
 * code blocks (useful after smd.js streaming finishes).
 */
export function highlightCodeBlocks(container: HTMLElement): void {
  container.querySelectorAll<HTMLElement>('pre code:not(.hljs)').forEach((block) => {
    hljs.highlightElement(block);
  });
}

/**
 * Attach click handlers to code copy buttons within a container.
 * Must be called after rendering markdown with renderMarkdown() since
 * DOMPurify strips inline onclick handlers for security.
 */
export function attachCodeCopyHandlers(container: HTMLElement): void {
  container.querySelectorAll<HTMLButtonElement>('[data-copy-code]').forEach((btn) => {
    if (btn.dataset.copyHandlerAttached) return;
    btn.dataset.copyHandlerAttached = 'true';
    btn.addEventListener('click', () => {
      const wrapper = btn.closest('.code-block-wrapper');
      const code = wrapper?.querySelector('code');
      if (code) {
        const text = code.textContent || '';
        navigator.clipboard.writeText(text).then(() => {
          btn.textContent = 'Copied!';
          setTimeout(() => {
            btn.textContent = 'Copy';
          }, 1500);
        });
      }
    });
  });
}
