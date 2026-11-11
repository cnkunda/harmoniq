import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * W5 regression guard: transcription confidence is a coarse band, never a raw
 * percentage. The four learner-facing surfaces must not reintroduce
 * `confidence * 100` numeric labels or bars.
 */
const REPO_ROOT = join(__dirname, '..', '..')

const CONFIDENCE_SURFACES = [
  'components/NoteDetailCard.tsx',
  'components/pulse/PulseStage.tsx',
  'components/pulse/PulseChordTimeline.tsx',
  'components/ListenStemPanel.tsx',
]

const RAW_PERCENT_PATTERNS = [
  /confidence\s*\*\s*100/g,
  /Math\.round\(\s*[^)]*confidence[^)]*\)\s*\*\s*100/g,
  /Label confidence:\s*\$/g,
  /Confidence:\s*\{[^}]*\}/g,
]

function readSource(relativePath: string): string {
  return readFileSync(join(REPO_ROOT, relativePath), 'utf8')
}

describe('transcription confidence display conformance', () => {
  for (const surface of CONFIDENCE_SURFACES) {
    it(`${surface} renders a band, not a raw percentage`, () => {
      const source = readSource(surface)
      for (const pattern of RAW_PERCENT_PATTERNS) {
        const hits = source.match(pattern) ?? []
        expect(hits, `${surface} matched ${pattern}`).toEqual([])
      }
    })
  }

  it('learner-facing band labels never claim a good match', () => {
    const source = readSource('src/session/transcriptionConfidence.ts')
    expect(source).not.toMatch(/good match/i)
    expect(source).toContain('check by ear')
  })
})
