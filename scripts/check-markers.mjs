// Validates that every in-code marker (TODO/FIXME/HACK/XXX/@deprecated) in
// tracked source carries an M-xx ID registered in techdebt/MARKERS.md.
// Run with `npm run check:markers`; CI runs it in the lint job.

import { readdirSync, readFileSync } from 'node:fs'
import { dirname, extname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

/** Repository root (parent of `scripts/`). */
export const REPO_ROOT = join(HERE, '..')

/** Directories scanned for markers. Docs, tests, and vendored code are excluded. */
export const SCAN_DIRS = ['app', 'src', 'components', 'types', 'backend/app', 'backend/scripts']

/** Directories that never contain authored source. */
export const SKIP_DIRS = new Set([
  'node_modules',
  '.git',
  '.expo',
  'dist',
  'coverage',
  'android',
  'ios',
  '__pycache__',
])

const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.py'])
const MARKER_RE = /\b(TODO|FIXME|HACK|XXX)\b/
const DEPRECATED_RE = /@deprecated\b/
const TRACKER_RE = /\bM-\d{2}\b/

/**
 * Find marker lines in a file's text.
 *
 * @param {string} text
 * @returns {Array<{ line: number, kind: string, text: string }>}
 */
export function findMarkers(text) {
  const markers = []
  text.split('\n').forEach((line, index) => {
    const match = line.match(MARKER_RE)
    if (match) {
      markers.push({ line: index + 1, kind: match[1], text: line.trim() })
      return
    }
    if (DEPRECATED_RE.test(line)) {
      markers.push({ line: index + 1, kind: '@deprecated', text: line.trim() })
    }
  })
  return markers
}

/**
 * Parse the M-xx IDs from the registry table in techdebt/MARKERS.md.
 *
 * @param {string} markdown
 * @returns {Set<string>}
 */
export function parseRegistry(markdown) {
  const ids = new Set()
  for (const line of markdown.split('\n')) {
    const match = line.match(/^\|\s*(M-\d{2})\s*\|/)
    if (match) ids.add(match[1])
  }
  return ids
}

/**
 * Validate the markers in one file against the registered IDs.
 *
 * @param {string} filePath Repo-relative path used in messages.
 * @param {string} text
 * @param {Set<string>} registryIds
 * @returns {{ violations: Array<{ file: string, line: number, message: string }>, referenced: Set<string> }}
 */
export function checkText(filePath, text, registryIds) {
  const violations = []
  const referenced = new Set()

  for (const marker of findMarkers(text)) {
    const idMatch = marker.text.match(TRACKER_RE)
    if (!idMatch) {
      violations.push({
        file: filePath,
        line: marker.line,
        message: `${marker.kind} marker has no M-xx tracking ID (register it in techdebt/MARKERS.md)`,
      })
      continue
    }
    const id = idMatch[0]
    if (!registryIds.has(id)) {
      violations.push({
        file: filePath,
        line: marker.line,
        message: `${marker.kind} references ${id}, which is not registered in techdebt/MARKERS.md`,
      })
    }
    referenced.add(id)
  }

  return { violations, referenced }
}

/**
 * List authored source files under the scanned directories.
 *
 * @param {string} [root]
 * @returns {string[]} Repo-relative paths.
 */
export function collectSourceFiles(root = REPO_ROOT) {
  const files = []

  const walk = (relDir) => {
    for (const entry of readdirSync(join(root, relDir), { withFileTypes: true })) {
      const relPath = join(relDir, entry.name)
      if (entry.isDirectory()) {
        if (SKIP_DIRS.has(entry.name)) continue
        walk(relPath)
      } else if (SOURCE_EXTENSIONS.has(extname(entry.name))) {
        files.push(relPath)
      }
    }
  }

  for (const dir of SCAN_DIRS) walk(dir)
  return files
}

/**
 * Validate the whole tree. Stale registry rows (IDs no longer used in source)
 * are reported so the registry cannot silently drift.
 *
 * @param {{ root?: string, registryPath?: string }} [options]
 * @returns {{ violations: Array<{ file: string, line: number, message: string }>, stale: string[] }}
 */
export function validateTree({ root = REPO_ROOT, registryPath = 'techdebt/MARKERS.md' } = {}) {
  const registryIds = parseRegistry(readFileSync(join(root, registryPath), 'utf8'))
  const violations = []
  const referenced = new Set()

  for (const relPath of collectSourceFiles(root)) {
    const text = readFileSync(join(root, relPath), 'utf8')
    const result = checkText(relPath.split(sep).join('/'), text, registryIds)
    violations.push(...result.violations)
    for (const id of result.referenced) referenced.add(id)
  }

  const stale = [...registryIds].filter((id) => !referenced.has(id)).sort()
  return { violations, stale }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { violations, stale } = validateTree()

  for (const violation of violations) {
    console.error(`[markers] ${violation.file}:${violation.line}: ${violation.message}`)
  }
  for (const id of stale) {
    console.error(`[markers] techdebt/MARKERS.md: ${id} is registered but not referenced in source`)
  }

  if (violations.length > 0 || stale.length > 0) {
    console.error(
      `[markers] ${violations.length} unowned marker(s), ${stale.length} stale registry row(s).`,
    )
    process.exit(1)
  }

  console.log('[markers] all in-code markers are tracked.')
}
