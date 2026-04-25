import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { ValidateEnv } from '@julr/vite-plugin-validate-env'
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  const allowedHosts = env.VITE_ALLOWED_HOSTS?.split(',').filter(Boolean) || []
  // Dev server binds to localhost by default — the Vite proxy forwards
  // /api/v1 to the ai-accounts sidecar (which manages CLI credentials and
  // auth tokens). Binding to 0.0.0.0 would expose those endpoints to the
  // LAN. Opt in explicitly with VITE_HOST=0.0.0.0 when you really need
  // LAN access (demos, headless VMs); also set VITE_ALLOWED_HOSTS and
  // AI_ACCOUNTS_API_KEY in that mode so the proxy isn't unauthenticated.
  const host = env.VITE_HOST || '127.0.0.1'

  return {
    plugins: [
      vue(),
      ValidateEnv({ configFile: 'src/env' }),
      VueI18nPlugin({
        include: resolve(dirname(fileURLToPath(import.meta.url)), './src/locales/**'),
      }),
    ],
    server: {
      host,
      port: 3000,
      strictPort: true,
      allowedHosts: allowedHosts.length ? allowedHosts : true,
      proxy: {
        '/api/v1': {
          target: 'http://127.0.0.1:20001',
          changeOrigin: true
        },
        '/api': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        '/admin': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        '/health': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        '/docs': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        '/openapi': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        }
      }
    },
    preview: {
      port: 3000,
      proxy: {
        '/api/v1': {
          target: 'http://127.0.0.1:20001',
          changeOrigin: true
        },
        '/api': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        '/admin': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        '/health': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        '/docs': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        },
        '/openapi': {
          target: 'http://127.0.0.1:20000',
          changeOrigin: true
        }
      }
    },
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules')) {
              if (id.includes('chart.js') || id.includes('chartjs-adapter-date-fns') || id.includes('date-fns')) {
                return 'vendor-chart'
              }
              if (id.includes('highlight.js')) {
                return 'vendor-highlight'
              }
              if (id.includes('@vue-flow') || id.includes('@dagrejs/dagre')) {
                return 'vendor-vue-flow'
              }
              if (id.includes('/marked/') || id.includes('dompurify')) {
                return 'vendor-markdown'
              }
              // All remaining node_modules in a single vendor chunk (Vue, etc.)
              return 'vendor-core'
            }
          }
        }
      }
    }
  }
})
