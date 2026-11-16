/**
 * Framework-free assertion helpers for the shared DB contract suite (Commit 17).
 * The web harness bundles this into a plain browser page, so it must not import
 * Vitest (or any other test framework). Errors carry expected/actual so both
 * the Vitest reporter and the Playwright failure report stay actionable.
 */

function formatValue(value: unknown): string {
  if (typeof value === 'string') return JSON.stringify(value)
  try {
    return JSON.stringify(value) ?? String(value)
  } catch {
    return String(value)
  }
}

function fail(expected: unknown, actual: unknown, message: string | undefined): never {
  throw new Error(`${message ?? 'assertion failed'} — expected ${formatValue(expected)}, got ${formatValue(actual)}`)
}

export interface ContractAssert {
  equal(actual: unknown, expected: unknown, message?: string): void
  deepEqual(actual: unknown, expected: unknown, message?: string): void
  truthy(value: unknown, message?: string): void
  /** Asserts the promise rejects with any Error (or rejects with a message containing `message`). */
  rejects(fn: () => Promise<unknown>, message?: string): Promise<void>
}

export function createContractAssert(): ContractAssert {
  return {
    equal(actual, expected, message) {
      if (actual !== expected) fail(expected, actual, message)
    },
    deepEqual(actual, expected, message) {
      const a = formatValue(actual)
      const b = formatValue(expected)
      if (a !== b) fail(b, a, message ?? 'deepEqual failed')
    },
    truthy(value, message) {
      if (!value) fail('truthy', value, message)
    },
    async rejects(fn, message) {
      try {
        await fn()
      } catch (e) {
        if (message) {
          const text = e instanceof Error ? e.message : String(e)
          if (!text.includes(message)) fail(`reject with "${message}"`, text, 'rejects failed')
        }
        return
      }
      fail('rejected promise', 'resolved', message ?? 'rejects failed')
    },
  }
}

export type ContractCaseResult = {
  name: string
  passed: boolean
  error: string | null
}
