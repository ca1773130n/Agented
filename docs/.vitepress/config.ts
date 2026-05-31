import { defineConfig } from 'vitepress'

const GITHUB = 'https://github.com/ca1773130n/Agented'

export default defineConfig({
  title: 'Agented',
  description:
    'A harness-engineering meta-layer for AI coding harnesses — orchestrating autonomous-agent workflows on a closed self-improving loop.',
  cleanUrls: true,

  // docs/ also holds pre-existing internal planning/spec/report markdown
  // that is NOT part of the public doc site (and isn't valid VitePress
  // content). Scope the build to the curated pages only.
  srcExclude: [
    'ai-accounts/**',
    'deploy/**',
    'perf/**',
    'plans/**',
    'superpowers/**',
    'full-ui-test-results.md',
    'monkey-test-results.md',
    'test-scenarios.md',
    'SECURITY.md',
  ],

  themeConfig: {
    socialLinks: [{ icon: 'github', link: GITHUB }],
  },

  locales: {
    root: {
      label: 'English',
      lang: 'en',
      themeConfig: {
        nav: [
          { text: 'Home', link: '/' },
          { text: 'Architecture', link: '/self-improving-harness-architecture' },
          { text: 'Blog', link: `${GITHUB}/blob/main/BLOG-self-improving-harness.md` },
        ],
        sidebar: [
          {
            text: 'Documentation',
            items: [
              {
                text: 'The Self-Improving Harness',
                link: '/self-improving-harness-architecture',
              },
            ],
          },
        ],
      },
    },

    ko: {
      label: '한국어',
      lang: 'ko',
      link: '/ko/',
      themeConfig: {
        nav: [
          { text: '홈', link: '/ko/' },
          { text: '아키텍처', link: '/ko/self-improving-harness-architecture' },
          { text: '블로그', link: `${GITHUB}/blob/main/BLOG-self-improving-harness.ko.md` },
        ],
        sidebar: [
          {
            text: '문서',
            items: [
              {
                text: '자기개선 하네스',
                link: '/ko/self-improving-harness-architecture',
              },
            ],
          },
        ],
      },
    },
  },
})
