import { defineConfig } from '@julr/vite-plugin-validate-env'
import { z } from 'zod'

export default defineConfig({
  validator: 'standard',
  schema: {
    VITE_ALLOWED_HOSTS: z.string().optional().default(''),
    // Future required variables can be added here.
    // Example: VITE_API_BASE_URL: z.string().url(),
  },
})
