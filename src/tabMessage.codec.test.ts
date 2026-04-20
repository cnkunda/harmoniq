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

  it('encodeTabMessage serializes setRenderPreset', () => {
    const msg: TabInboundMessage = { type: 'setRenderPreset', presetName: 'slow' }
    expect(JSON.parse(encodeTabMessage(msg))).toEqual({ type: 'setRenderPreset', presetName: 'slow' })
  })

  it('decodeTabMessage parses renderPresetApplied', () => {
    const raw = JSON.stringify({ type: 'renderPresetApplied', presetName: 'play' })
    expect(decodeTabMessage(raw)).toEqual({ type: 'renderPresetApplied', presetName: 'play' })
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

  it('encodeTabMessage serializes getSongDetails', () => {
    const msg: TabInboundMessage = { type: 'getSongDetails', requestId: 'r1' }
    expect(JSON.parse(encodeTabMessage(msg))).toEqual({ type: 'getSongDetails', requestId: 'r1' })
  })

  it('decodeTabMessage parses songDetails', () => {
    const raw = JSON.stringify({
      type: 'songDetails',
      requestId: 'r1',
      score: {
        title: 'T',
        tempoBpm: 120,
        sectionMarkers: [{ startMasterBarIndex: 0, label: 'Intro' }],
      },
    })
    expect(decodeTabMessage(raw)).toEqual({
      type: 'songDetails',
      requestId: 'r1',
      score: {
        title: 'T',
        artist: null,
        album: null,
        subTitle: null,
        words: null,
        music: null,
        tab: null,
        tempoBpm: 120,
        sectionMarkers: [{ startMasterBarIndex: 0, label: 'Intro' }],
      },
    })
  })

  it('decodeTabMessage parses songPlayback', () => {
    const raw = JSON.stringify({ type: 'songPlayback', masterBarIndex: 3, sectionLabel: 'Verse' })
    expect(decodeTabMessage(raw)).toEqual({
      type: 'songPlayback',
      masterBarIndex: 3,
      sectionLabel: 'Verse',
    })
  })

  it('encodeTabMessage serializes setSoundFontProfile', () => {
    const msg: TabInboundMessage = { type: 'setSoundFontProfile', profileId: 'fluid_r3_mono' }
    expect(JSON.parse(encodeTabMessage(msg))).toEqual({
      type: 'setSoundFontProfile',
      profileId: 'fluid_r3_mono',
    })
  })

  it('decodeTabMessage parses runtimeDiagnostics', () => {
    const raw = JSON.stringify({
      type: 'runtimeDiagnostics',
      windowMs: 5000,
      driftMs: 12.3,
      noteEventHz: 20,
      renderFps: 4.2,
      breachFlags: ['DRIFT_MS'],
    })
    expect(decodeTabMessage(raw)).toEqual({
      type: 'runtimeDiagnostics',
      windowMs: 5000,
      driftMs: 12.3,
      noteEventHz: 20,
      renderFps: 4.2,
      breachFlags: ['DRIFT_MS'],
    })
  })

  it('decodeTabMessage parses soundFontLoad with profile + progress', () => {
    const raw = JSON.stringify({
      type: 'soundFontLoad',
      status: 'loading',
      profileId: 'general_user',
      loaded: 128,
      total: 4096,
    })
    expect(decodeTabMessage(raw)).toEqual({
      type: 'soundFontLoad',
      status: 'loading',
      profileId: 'general_user',
      loaded: 128,
      total: 4096,
      message: undefined,
    })
  })
})
