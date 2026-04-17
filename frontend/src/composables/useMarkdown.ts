import { Marked, type Tokens } from 'marked';
import DOMPurify from 'dompurify';
import { createHighlighterCoreSync } from 'shiki/core';
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript';
import vitesseDark from 'shiki/themes/vitesse-dark.mjs';
import langJavascript from 'shiki/langs/javascript.mjs';
import langTypescript from 'shiki/langs/typescript.mjs';
import langPython from 'shiki/langs/python.mjs';
import langBash from 'shiki/langs/bash.mjs';
import langJson from 'shiki/langs/json.mjs';
import langCss from 'shiki/langs/css.mjs';
import langHtml from 'shiki/langs/html.mjs';
import langSql from 'shiki/langs/sql.mjs';
import langYaml from 'shiki/langs/yaml.mjs';
import langMarkdown from 'shiki/langs/markdown.mjs';
import langDiff from 'shiki/langs/diff.mjs';
import langGo from 'shiki/langs/go.mjs';
import langRust from 'shiki/langs/rust.mjs';
import langJava from 'shiki/langs/java.mjs';
import langCsharp from 'shiki/langs/csharp.mjs';
import langRuby from 'shiki/langs/ruby.mjs';
import langPhp from 'shiki/langs/php.mjs';
import langShell from 'shiki/langs/shellscript.mjs';
import langToml from 'shiki/langs/toml.mjs';
import langXml from 'shiki/langs/xml.mjs';
import langJsx from 'shiki/langs/jsx.mjs';
import langTsx from 'shiki/langs/tsx.mjs';
import langVue from 'shiki/langs/vue.mjs';
import langDockerfile from 'shiki/langs/dockerfile.mjs';

const THEME = 'vitesse-dark';

// Language alias mapping for common shorthand names
const LANG_ALIASES: Record<string, string> = {
  js: 'javascript',
  ts: 'typescript',
  py: 'python',
  sh: 'bash',
  zsh: 'bash',
  yml: 'yaml',
  md: 'markdown',
  rs: 'rust',
  cs: 'csharp',
  rb: 'ruby',
  text: 'plaintext',
  plaintext: 'plaintext',
  dockerfile: 'dockerfile',
};

const shiki = createHighlighterCoreSync({
  themes: [vitesseDark],
  langs: [
    langJavascript, langTypescript, langPython, langBash,
    langJson, langCss, langHtml, langSql, langYaml,
    langMarkdown, langDiff, langGo, langRust, langJava,
    langCsharp, langRuby, langPhp, langShell, langToml,
    langXml, langJsx, langTsx, langVue, langDockerfile,
  ],
  engine: createJavaScriptRegexEngine(),
});

const loadedLangs = new Set(shiki.getLoadedLanguages());

function resolveLanguage(lang: string | undefined): string | null {
  if (!lang) return null;
  const lower = lang.toLowerCase();
  const mapped = LANG_ALIASES[lower] || lower;
  if (loadedLangs.has(mapped)) return mapped;
  if (loadedLangs.has(lower)) return lower;
  return null;
}

function highlightCode(code: string, lang: string | undefined): string {
  const resolved = resolveLanguage(lang);
  if (resolved && resolved !== 'plaintext') {
    try {
      return shiki.codeToHtml(code, { lang: resolved, theme: THEME });
    } catch {
      // fall through to plain
    }
  }
  // Plaintext fallback — wrap in the same structure shiki would produce
  const escaped = code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return `<pre class="shiki vitesse-dark" style="background-color:#121212"><code>${escaped}</code></pre>`;
}

const marked = new Marked({
  breaks: true,
  gfm: true,
  renderer: {
    code(token: Tokens.Code) {
      const lang = token.lang;
      const text = token.text;
      const displayLang = lang || 'code';
      const highlighted = highlightCode(text, lang);
      return `<div class="code-block-wrapper"><div class="code-block-header"><span class="code-lang">${displayLang}</span><button class="code-copy-btn" data-copy-code="true">Copy</button></div>${highlighted}</div>`;
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

/**
 * Render markdown to sanitized HTML.
 * Uses DOMPurify to prevent XSS — all output is sanitized before use.
 */
export function renderMarkdown(content: string): string {
  const raw = marked.parse(content) as string;
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['class', 'target', 'rel', 'data-copy-code', 'style'],
    ADD_TAGS: ['span'],
  });
}

/**
 * Post-process a DOM container to apply shiki highlighting to any
 * un-highlighted code blocks (useful after smd.js streaming finishes).
 */
export function highlightCodeBlocks(container: HTMLElement): void {
  container.querySelectorAll<HTMLElement>('pre code:not([data-shiki])').forEach((block) => {
    const lang = block.className?.match(/language-(\w+)/)?.[1];
    const code = block.textContent || '';
    const resolved = resolveLanguage(lang);
    if (resolved && resolved !== 'plaintext') {
      try {
        const highlighted = shiki.codeToHtml(code, { lang: resolved, theme: THEME });
        // Safely replace the pre>code with shiki output via DOMPurify
        const pre = block.closest('pre');
        if (pre?.parentElement) {
          const sanitized = DOMPurify.sanitize(highlighted, {
            ADD_ATTR: ['class', 'style'],
            ADD_TAGS: ['span'],
          });
          const wrapper = document.createElement('div');
          wrapper.textContent = ''; // clear safely
          // Use DOMPurify-sanitized content
          const template = document.createElement('template');
          template.innerHTML = sanitized;
          const newNode = template.content.firstElementChild;
          if (newNode) {
            pre.parentElement.replaceChild(newNode, pre);
          }
        }
        return;
      } catch {
        // fall through
      }
    }
    block.setAttribute('data-shiki', 'plain');
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
        }).catch((err) => {
          console.warn('Clipboard write failed:', err);
        });
      }
    });
  });
}
