import { readdirSync, readFileSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * Commit 10 boundary guard: backend API calls must go through `src/api/`.
 * Only direct `fetch(`${API_BASE_URL}…`)` calls are flagged; asset fetches
 * (`fetch(uri)`), auth redirect builders, and `/lesson-file` URL helpers are
 * intentionally outside this rule.
 */
const REPO_ROOT = join(__dirname, '..', '..')
const SCAN_DIRS = ['app', 'src', 'components']
const PRUNED_DIRECTORIES = new Set([
  'node_modules',
  '.expo',
  '.git',
  'dist',
  'coverage',
  'artifacts',
  'test-results',
])
const DIRECT_API_FETCH = /fetch\s*\(\s*`\$\{API_BASE_URL\}/

function stripComments(source: string): string {
  const withoutBlocks = source.replace(/\/\*[\s\S]*?\*\//g, '')
  return withoutBlocks
    .split('\n')
    .map((line) => {
      const idx = line.indexOf('//')
      return idx === -1 ? line : line.slice(0, idx)
    })
    .join('\n')
}

function walk(dir: string, out: string[]): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (PRUNED_DIRECTORIES.has(entry.name)) continue
    const abs = join(dir, entry.name)
    if (entry.isDirectory()) {
      walk(abs, out)
    } else if (entry.isFile() && (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx'))) {
      out.push(abs)
    }
  }
  return out
}

function isTestFile(rel: string): boolean {
  return /\.test\.(ts|tsx)$/.test(rel)
}

describe('apiBoundary (Commit 10)', () => {
  it('keeps direct ${API_BASE_URL} fetches inside src/api', () => {
    const offenders: string[] = []
    for (const dir of SCAN_DIRS) {
      for (const abs of walk(join(REPO_ROOT, dir), [])) {
        const rel = relative(REPO_ROOT, abs).split(sep).join('/')
        if (rel.startsWith('src/api/') || isTestFile(rel)) continue
        const code = stripComments(readFileSync(abs, 'utf8'))
        code.split('\n').forEach((line, index) => {
          if (DIRECT_API_FETCH.test(line)) offenders.push(`${rel}:${index + 1}`)
        })
      }
    }
    expect(offenders).toEqual([])
  }, 60_000)
})
