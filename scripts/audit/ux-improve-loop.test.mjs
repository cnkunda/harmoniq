import { describe, it, expect } from 'vitest'
import path from 'node:path'
import os from 'node:os'
import { appFileToRouteCandidates, parseVisionVerdict } from './ux-improve-loop.mjs'

const APP_DIR = path.join(process.cwd(), 'app')

function candidate(rel) {
  return appFileToRouteCandidates(path.join(APP_DIR, ...rel.split('/')))
}

describe('parseVisionVerdict', () => {
  it('returns pass for a clean describe-register response', () => {
    const result = parseVisionVerdict(
      'The screenshot shows a music app with a dark brown and cream theme. ' +
        'The app has a simple and clean design, with a clear and easy-to-read interface.',
    )
    expect(result).toEqual({ verdict: 'pass', defects: [] })
  })

  it('returns pass for the everything-looks-fine sentinel', () => {
    expect(parseVisionVerdict('Everything looks fine.')).toEqual({
      verdict: 'pass',
      defects: [],
    })
  })

  it('treats an empty Ollama dict leak as a parse failure, not a pass', () => {
    const result = parseVisionVerdict(
      "{'model': 'moondream:latest', 'message': {'role': 'assistant', 'content': ''}, 'done': True}",
    )
    expect(result.verdict).toBeNull()
  })

  it('returns fail with defect sentences for a real defect response', () => {
    const result = parseVisionVerdict(
      'The text at the bottom is cut off at the edge of the screen. ' +
        'The buttons are misaligned with each other.',
    )
    expect(result.verdict).toBe('fail')
    expect(result.defects).toHaveLength(2)
    expect(result.defects[0]).toContain('cut off')
    expect(result.defects[1]).toContain('misaligned')
  })

  it('ignores negated defect mentions', () => {
    const result = parseVisionVerdict(
      'There is no overlapping text and nothing is cut off. The layout is clean.',
    )
    expect(result).toEqual({ verdict: 'pass', defects: [] })
  })

  it('strips proxy stderr diagnostics leaked through wsl.exe', () => {
    const result = parseVisionVerdict(
      'SEARCH: File exists at /mnt/c/foo.png\nKEYS: 9 backends available\n[viewport.png]\nEverything looks fine.',
    )
    expect(result).toEqual({ verdict: 'pass', defects: [] })
  })

  it('caps defects at five sentences', () => {
    const sentences = Array.from({ length: 8 }, (_, i) => `Row ${i} text is overlapping row ${i + 1}.`).join(' ')
    const result = parseVisionVerdict(sentences)
    expect(result.verdict).toBe('fail')
    expect(result.defects).toHaveLength(5)
  })

  it('returns null for empty input', () => {
    expect(parseVisionVerdict('')).toEqual({ verdict: null, defects: [] })
    expect(parseVisionVerdict(undefined)).toEqual({ verdict: null, defects: [] })
  })
})

describe('ux-improve-loop route mapping', () => {
  it('maps a root index to "/"', () => {
    const routes = candidate('index.tsx')
    expect(routes.length).toBe(1)
    expect(routes).toContain('/')
  })

  it('maps nested screens and skips route groups', () => {
    expect(candidate('(tabs)/settings.tsx')).toContain('/settings')
    expect(candidate('(tabs)/discover.tsx')).toContain('/discover')
  })

  it('maps dynamic screen files to concrete manual routes at the same depth', () => {
    const routes = candidate('onboarding/phrase/[index].tsx')
    expect(routes.length).toBeGreaterThan(0)
  })

  it('skips non-route files like _layout and +html', () => {
    expect(candidate('(tabs)/_layout.tsx')).toEqual([])
  })

  it('returns empty for files outside app/', () => {
    const outside = appFileToRouteCandidates(path.join(os.tmpdir(), 'foo.tsx'))
    expect(outside).toEqual([])
  })
})
