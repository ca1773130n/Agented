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
    // Blog posts are long-form essays viewed on GitHub (the nav "Blog"
    // link points to the GitHub blob), not built site pages — same as the
    // repo-root BLOG-*.md posts.
    'BLOG-*.md',
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
          { text: 'Tutorial', link: '/self-improving-harness-tutorial' },
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
              {
                text: 'Tutorial: Watch It Improve Itself',
                link: '/self-improving-harness-tutorial',
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
          { text: '튜토리얼', link: '/ko/self-improving-harness-tutorial' },
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
              {
                text: '튜토리얼: 스스로 개선되는 과정',
                link: '/ko/self-improving-harness-tutorial',
              },
            ],
          },
        ],
      },
    },

    ja: {
      label: '日本語',
      lang: 'ja',
      link: '/ja/',
      themeConfig: {
        nav: [
          { text: 'ホーム', link: '/ja/' },
          { text: 'アーキテクチャ', link: '/ja/self-improving-harness-architecture' },
          { text: 'チュートリアル', link: '/ja/self-improving-harness-tutorial' },
          { text: 'ブログ', link: `${GITHUB}/blob/main/BLOG-self-improving-harness.md` },
        ],
        sidebar: [
          {
            text: 'ドキュメント',
            items: [
              {
                text: '自己改善ハーネス',
                link: '/ja/self-improving-harness-architecture',
              },
              {
                text: 'チュートリアル: 自己改善の流れを見る',
                link: '/ja/self-improving-harness-tutorial',
              },
            ],
          },
        ],
      },
    },

    zh: {
      label: '中文',
      lang: 'zh',
      link: '/zh/',
      themeConfig: {
        nav: [
          { text: '首页', link: '/zh/' },
          { text: '架构', link: '/zh/self-improving-harness-architecture' },
          { text: '教程', link: '/zh/self-improving-harness-tutorial' },
          { text: '博客', link: `${GITHUB}/blob/main/BLOG-self-improving-harness.md` },
        ],
        sidebar: [
          {
            text: '文档',
            items: [
              {
                text: '自我改进 harness',
                link: '/zh/self-improving-harness-architecture',
              },
              {
                text: '教程：观察 harness 的自我改进',
                link: '/zh/self-improving-harness-tutorial',
              },
            ],
          },
        ],
      },
    },
  },
})
