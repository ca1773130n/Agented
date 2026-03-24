import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'happy-dom',
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{ts,vue}'],
      exclude: ['src/main.ts', 'src/**/*.d.ts', 'src/test/**'],
      thresholds: {
        // Tour state machine: 100% branch achieved; function/line relaxed because
        // XState guard stubs (isWorkspaceConfigured, etc.) are `() => false` defaults
        // overridden via machine.provide() at runtime — V8 never covers the originals
        'src/machines/tourMachine.ts': {
          branches: 90,
          functions: 35,
          lines: 65,
        },
        // Tour composable: strict branch coverage, moderate function/line
        'src/composables/useTourMachine.ts': {
          branches: 90,
          functions: 80,
          lines: 80,
        },
      },
    },
    setupFiles: ['./src/test/setup.ts']
  }
})
