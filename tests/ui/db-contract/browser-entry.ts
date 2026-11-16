/**
 * Commit 17: shared DB contract suite — web leg browser entry.
 * Bundled with Vite (IIFE, in-memory) by `tests/ui/db-contract.web.spec.ts`,
 * injected into a blank same-origin page, and executed against the real
 * `client.web` + real Chromium IndexedDB. Results land on
 * `window.__dbContractResult` for the Playwright spec to assert on.
 */

import type { ContractCaseResult } from '@/src/db/contract/contractAssert'
import { runDbContractCases } from '@/src/db/contract/dbContractCases'
import * as webClient from '@/src/db/client.web'

declare global {
  var __dbContractResult: { total: number; failed: number; failures: ContractCaseResult[] } | undefined
}

export async function runDbContractBrowserSuite(): Promise<{
  total: number
  failed: number
  failures: ContractCaseResult[]
}> {
  await webClient.initDb()
  await webClient.clearAllPracticeData()
  const results = await runDbContractCases(webClient)
  const failures = results.filter((r) => !r.passed)
  return { total: results.length, failed: failures.length, failures }
}

void (async () => {
  try {
    window.__dbContractResult = await runDbContractBrowserSuite()
  } catch (e) {
    const error = e instanceof Error ? e.message : String(e)
    console.error('[dbContract/web] suite crashed before reporting', e)
    window.__dbContractResult = {
      total: 0,
      failed: 1,
      failures: [{ name: 'browser-suite', passed: false, error }],
    }
  }
})()
