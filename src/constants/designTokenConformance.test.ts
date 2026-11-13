import { readdirSync, readFileSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Commit 154 regression guard: `src/constants/colors.ts` is the single source
 * of color truth and styling follows the WoodGradient / className conventions.
 *
 * The guard covers hex literals AND functional-notation color literals in
 * `ts`/`tsx`. Every value moved here keeps its exact rendered pixels — new
 * colors go into `colors.ts` first, then are referenced by name.
 *
 * Justified exceptions (do not extend without a PRIORITIES.md commit):
 * - `tailwind.config.js`: defines the class-to-token mapping itself (not scanned,
 *   this guard only walks `ts`/`tsx`).
 * - `backend/`: Python backend, out of scope for this frontend-design guard (also
 *   contains WSL symlinks that are unreadable from Windows checkouts).
 * - `app/_layout.tsx`: registers `cssInterop(LinearGradient)`; the raw import is
 *   infrastructure, not a wrapper bypass.
 * - `assets/alphatab-harness/index.html`: static webview asset that cannot import
 *   TS tokens (not scanned); keep its player rules in sync with
 *   `src/constants/alphaTabPlayerUi.ts` by hand.
 * - `StyleSheet.absoluteFillObject`: not `StyleSheet.create`, has no className
 *   equivalent, and is therefore not flagged by this guard.
 * - Computed color strings (e.g. the dynamic scale-degree tint in
 *   `FretboardDiagram.tsx`): generated from variables at runtime, not hardcoded
 *   literals, and therefore not flaggable by a literal scan.
 */
const REPO_ROOT = join(__dirname, '..', '..')

const COLOR_SOURCE = 'src/constants/colors.ts'
const GRADIENT_WRAPPER = 'components/WoodGradient.tsx'
const GRADIENT_INTEROP = 'app/_layout.tsx'

const HEX_PATTERN = /#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?:[0-9a-fA-F]{2})?\b/g
const RGB_FUNCTION_PATTERN = /\brgba?\(\s*\d/g
const GRADIENT_IMPORT_PATTERN = /from\s+['"]expo-linear-gradient['"]/g
const STYLESHEET_CREATE_PATTERN = /StyleSheet\s*\.\s*create\s*\(/g

function toRepoPath(abs: string): string {
  return relative(REPO_ROOT, abs).split(sep).join('/')
}

// Directories that cannot contain app source and are expensive to walk
// (native projects, generated bundles, caches, data/model artifacts).
const PRUNED_DIRECTORIES = new Set([
  'node_modules',
  '.expo',
  '.git',
  'backend',
  'android',
  'ios',
  'artifacts',
  'test-results',
  'dist',
  'coverage',
  '.ruff_cache',
  '.pytest_cache',
  'data',
  'docker',
  'cerebrium_w2',
  'public',
  'assets',
  'techdebt',
])

function walkTsFiles(dir: string, out: string[]): string[] {
  // `withFileTypes` avoids a statSync per entry, which is the dominant cost of
  // walking the repo on Windows-mounted filesystems.
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (PRUNED_DIRECTORIES.has(entry.name)) continue
    const abs = join(dir, entry.name)
    if (entry.isDirectory()) {
      walkTsFiles(abs, out)
    } else if (entry.isFile() && (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx'))) {
      out.push(abs)
    }
  }
  return out
}

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

function findHits(pattern: RegExp, code: string): string[] {
  const hits: string[] = []
  for (const line of code.split('\n')) {
    const matches = line.match(pattern)
    if (matches) hits.push(...matches)
  }
  return hits
}

// The repo walk + read + comment strip is the expensive part — computed once
// and shared by all four assertions (the scan alone ran ~40s+ under load).
type ScannedFile = { abs: string; rel: string; stripped: string }
let scanned: ScannedFile[] | null = null
function scanRepo(): ScannedFile[] {
  if (scanned) return scanned
  scanned = walkTsFiles(REPO_ROOT, []).map((abs) => ({
    abs,
    rel: toRepoPath(abs),
    stripped: stripComments(readFileSync(abs, 'utf8')),
  }))
  return scanned
}

describe('designTokenConformance (Commit 154)', () => {
  it('has zero hex color literals outside the palette source', () => {
    const offenders: string[] = []
    for (const { rel, stripped } of scanRepo()) {
      if (rel === COLOR_SOURCE) continue
      const hits = findHits(HEX_PATTERN, stripped)
      if (hits.length > 0) offenders.push(`${rel}: ${hits.join(', ')}`)
    }
    expect(offenders).toEqual([])
  }, 60_000)

  it('has zero functional-notation color literals outside the palette source', () => {
    const offenders: string[] = []
    for (const { rel, stripped } of scanRepo()) {
      if (rel === COLOR_SOURCE) continue
      const hits = findHits(RGB_FUNCTION_PATTERN, stripped)
      if (hits.length > 0) offenders.push(`${rel}: ${hits.join(', ')}`)
    }
    expect(offenders).toEqual([])
  }, 60_000)

  it('imports expo-linear-gradient only in the wrapper and the interop registration', () => {
    const offenders: string[] = []
    for (const { rel, stripped } of scanRepo()) {
      if (rel === GRADIENT_WRAPPER || rel === GRADIENT_INTEROP) continue
      const hits = findHits(GRADIENT_IMPORT_PATTERN, stripped)
      if (hits.length > 0) offenders.push(rel)
    }
    expect(offenders).toEqual([])
  }, 60_000)

  it('has zero StyleSheet.create calls', () => {
    const offenders: string[] = []
    for (const { rel, stripped } of scanRepo()) {
      const hits = findHits(STYLESHEET_CREATE_PATTERN, stripped)
      if (hits.length > 0) offenders.push(rel)
    }
    expect(offenders).toEqual([])
  }, 60_000)
})
