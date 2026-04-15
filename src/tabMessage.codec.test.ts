import { describe, expect, it } from 'vitest'

import { decodeTabMessage, encodeTabMessage, type TabInboundMessage } from '@/types/tabMessage'

describe('tabMessage encode/decode', () => {
  it('encodeTabMessage serializes scrollMasterBarIntoView for host → harness', () => {
    const msg: TabInboundMessage = { type: 'scrollMasterBarIntoView', barIndex: 4 }
    const raw = encodeTabMessage(msg)
    const parsed = JSON.parse(raw) as { type: string; barIndex: number }
    expect(parsed).toEqual({ type: 'scrollMasterBarIntoView', barIndex: 4 })
  })

  it('encodeTabMessage serializes syncTimelineMs', () => {
    const msg: TabInboundMessage = { type: 'syncTimelineMs', positionMs: 12_345 }
    const parsed = JSON.parse(encodeTabMessage(msg)) as { type: string; positionMs: number }
    expect(parsed).toEqual({ type: 'syncTimelineMs', positionMs: 12_345 })
  })

  it('decodeTabMessage parses noteEvent from harness JSON', () => {
    const raw = JSON.stringify({
      type: 'noteEvent',
      midi: 64,
      beat: 2,
      string: 2,
      fret: 5,
      fromScoreTap: true,
    })
    expect(decodeTabMessage(raw)).toEqual({
      type: 'noteEvent',
      midi: 64,
      beat: 2,
      string: 2,
      fret: 5,
      fromScoreTap: true,
    })
  })

  it('returns null for invalid JSON', () => {
    expect(decodeTabMessage('not json')).toBeNull()
  })
})
