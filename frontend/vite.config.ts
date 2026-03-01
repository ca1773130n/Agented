import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  const allowedHosts = env.VITE_ALLOWED_HOSTS?.split(',').filter(Boolean) || []

  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 3000,
      strictPort: true,
      allowedHosts,
      proxy: {
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
