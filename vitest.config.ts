import path from 'node:path'

import { defineConfig } from 'vitest/config'
import { reactNative } from 'vitest-native'

export default defineConfig({
  plugins: [reactNative()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx', 'components/**/*.test.tsx', 'scripts/**/*.test.mjs'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
      reporter: ['text', 'html', 'json'],
      thresholds: {
        lines: 47.5,
        branches: 40.3,
      },
    },
  },
  resolve: {
    alias: {
      // The plugin's Metro platform order resolves .native.ts before .ts, which would
      // flip the shared client to client.native.ts (expo-sqlite) in every test.
      // Pin the TypeScript resolution (client.ts -> web impl); the contract suite
      // imports client.native / client.web explicitly and is unaffected.
      '@/src/db/client': path.resolve(__dirname, 'src/db/client.ts'),
      '@': path.resolve(__dirname),
    },
  },
})
