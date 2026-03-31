import path from 'node:path'

import { loadProjectEnv } from '@expo/env'
import type { ConfigContext, ExpoConfig } from 'expo/config'

/**
 * Hydrate `process.env` from repo-root `.env*` files before reading `EXPO_PUBLIC_*`.
 *
 * `app.config.ts` runs in Node when Expo evaluates config (not inside the Metro bundle).
 * `EXPO_PUBLIC_*` inlining applies to app JS; without this step, `process.env.EXPO_PUBLIC_API_URL`
 * is often unset here unless the parent process already loaded dotenv — so `extra` would always
 * fall back to localhost. `loadProjectEnv` matches Expo CLI's `.env` resolution (`.env.local`,
 * `.env.development`, etc.).
 */
loadProjectEnv(path.dirname(__filename), { silent: true })

/**
 * `extra.apiBaseUrl` is read at runtime via `expo-constants` in `src/config.ts`.
 * Set `EXPO_PUBLIC_API_URL` in `.env` (see `.env.example`) for LAN/device testing.
 */
const audioApiPlugin: NonNullable<ExpoConfig['plugins']>[number] = [
  'react-native-audio-api',
  {
    iosMicrophonePermission:
      'Harmoniq uses the microphone to hear your instrument and show live pitch while you practice.',
    androidPermissions: ['android.permission.RECORD_AUDIO'],
  },
]

export default ({ config }: ConfigContext): ExpoConfig =>
  ({
    ...config,
    plugins: [...(config.plugins ?? []), audioApiPlugin],
    extra: {
      ...config.extra,
      apiBaseUrl: process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000',
    },
  }) as ExpoConfig
