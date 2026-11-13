import { describe, expect, it } from 'vitest'

import { checkText, findMarkers, parseRegistry } from './check-markers.mjs'

describe('findMarkers', () => {
  it('finds TODO/FIXME/HACK/XXX and @deprecated markers with line numbers', () => {
    const text = ['const a = 1', '// TODO: one', '// FIXME: two', '// HACK: three', '// XXX: four', '/** @deprecated five */'].join('\n')
    expect(findMarkers(text)).toEqual([
      { line: 2, kind: 'TODO', text: '// TODO: one' },
      { line: 3, kind: 'FIXME', text: '// FIXME: two' },
      { line: 4, kind: 'HACK', text: '// HACK: three' },
      { line: 5, kind: 'XXX', text: '// XXX: four' },
      { line: 6, kind: '@deprecated', text: '/** @deprecated five */' },
    ])
  })

  it('ignores embedded tokens such as bpmXXX', () => {
    expect(findMarkers('# prog_NNNN_bpmXXX.mid')).toEqual([])
  })
})

describe('checkText', () => {
  const registry = new Set(['M-01', 'M-04'])

  it('flags markers without a tracking ID', () => {
    const result = checkText('src/a.ts', '// TODO: fix this', registry)
    expect(result.violations).toEqual([
      {
        file: 'src/a.ts',
        line: 1,
        message: 'TODO marker has no M-xx tracking ID (register it in techdebt/MARKERS.md)',
      },
    ])
  })

  it('accepts a registered tracking ID and reports it as referenced', () => {
    const result = checkText('src/a.ts', '// TODO(M-01): fix this\n/** @deprecated M-04 — use the new API */', registry)
    expect(result.violations).toEqual([])
    expect(result.referenced).toEqual(new Set(['M-01', 'M-04']))
  })

  it('flags a tracking ID that is not in the registry', () => {
    const result = checkText('src/a.ts', '// TODO(M-99): fix this', registry)
    expect(result.violations[0]?.message).toContain('M-99')
    expect(result.violations[0]?.message).toContain('not registered')
  })
})

describe('parseRegistry', () => {
  it('reads IDs only from table rows', () => {
    const markdown = [
      '# Registry',
      'M-01 appears in prose and must be ignored',
      '| ID | Location |',
      '| --- | --- |',
      '| M-01 | `app/a.tsx:1` |',
      '| M-04 | `src/b.ts:2` |',
    ].join('\n')
    expect(parseRegistry(markdown)).toEqual(new Set(['M-01', 'M-04']))
  })
})
