/**
 * Commit 17: shared DB contract suite — native leg.
 * Runs `DB_CONTRACT_CASES` against `client.native` with `expo-sqlite` mocked by
 * a `node:sqlite` (DatabaseSync) adapter, so the real SQLite semantics of the
 * native client are exercised in Vitest without a device or Expo runtime.
 *
 * The real `expo-sqlite` module graph pulls in react-native (unparseable in
 * Vitest), so the mock factory must replace it before `client.native` loads.
 * Same for `expo-constants`: `config.ts` reaches it through the `lessonStore`
 * dynamic import inside `getHomeSuggestion`. If `node:sqlite` is unavailable
 * (Node < 22.13), the import below fails and the suite fails loudly — no skip.
 */
import { DatabaseSync, type SQLInputValue } from 'node:sqlite'

import { beforeEach, describe, it, vi } from 'vitest'

import { createContractAssert } from '@/src/db/contract/contractAssert'
import { DB_CONTRACT_CASES } from '@/src/db/contract/dbContractCases'
import type { HarmoniqDbClient } from '@/src/db/harmoniqDbClient'
import * as nativeClient from '@/src/db/client.native'

// `__DEV__` is a Metro bundle global; define it for the Vitest node environment
// so `migrations.ts` / `client.native` catch paths can evaluate it.
;(globalThis as { __DEV__?: boolean }).__DEV__ = true

vi.mock('expo-constants', () => ({ default: { expoConfig: undefined } }))

vi.mock('expo-sqlite', () => {
  let db: DatabaseSync | null = null
  const normalize = (params: unknown[]): SQLInputValue[] =>
    params.map((p) => (p === undefined ? null : (p as SQLInputValue)))
  const adapter = {
    async execAsync(source: string): Promise<void> {
      db!.exec(source)
    },
    async runAsync(source: string, ...params: unknown[]) {
      return db!.prepare(source).run(...normalize(params))
    },
    async getFirstAsync<T>(source: string, ...params: unknown[]): Promise<T | undefined> {
      return db!.prepare(source).get(...normalize(params)) as T | undefined
    },
    async getAllAsync<T>(source: string, ...params: unknown[]): Promise<T[]> {
      return db!.prepare(source).all(...normalize(params)) as T[]
    },
    async withTransactionAsync(fn: () => Promise<void>): Promise<void> {
      db!.exec('BEGIN')
      try {
        await fn()
        db!.exec('COMMIT')
      } catch (e) {
        try {
          db!.exec('ROLLBACK')
        } catch (rollbackError) {
          console.error('[dbContract/native] rollback failed', rollbackError)
        }
        throw e
      }
    },
  }
  return {
    openDatabaseAsync: async () => {
      if (!db) db = new DatabaseSync(':memory:')
      return adapter
    },
  }
})

describe('DB contract — native (SQLite via node:sqlite)', () => {
  beforeEach(async () => {
    await nativeClient.clearAllPracticeData()
  })

  for (const testCase of DB_CONTRACT_CASES) {
    it(`case: ${testCase.name}`, async () => {
      await testCase.run(nativeClient as HarmoniqDbClient, createContractAssert())
    })
  }
})
