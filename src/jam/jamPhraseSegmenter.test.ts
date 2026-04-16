import { describe, expect, it, vi } from 'vitest'

import type { PitchReading } from '@/src/pitch/pitchTypes'
import { createJamPhraseSegmenter } from '@/src/jam/jamPhraseSegmenter'

function readingHz(hz: number, rms = 0.05): PitchReading {
  const midiFloat = 69 + 12 * Math.log2(hz / 440)
  const rounded = Math.round(midiFloat)
  return {
    hz,
    midi: rounded,
    cents: Math.round((midiFloat - rounded) * 100),
    noteName: 'X',
    rms,
  }
}

function silent(rms = 0.001): PitchReading {
  return { midi: 0, cents: 0, noteName: '', rms }
}

describe('createJamPhraseSegmenter', () => {
  it('closes a phrase after sustained silence', () => {
    const closed: { startTime: number; endTime: number; notes: { midi: number }[] }[] = []
    const seg = createJamPhraseSegmenter({
      silenceEndMs: 500,
      onPhraseClosed: (p) => closed.push(p),
    })

    let t = 0
    seg.push(readingHz(440), t, 0)
    t += 100
    seg.push(readingHz(440), t, 100)
    t += 100
    seg.push(readingHz(523.25), t, 200)
    t = 250
    while (t <= 800) {
      seg.push(silent(), t, 250 + (t - 250))
      t += 50
    }
    expect(closed.length).toBe(1)
    expect(closed[0]!.notes.length).toBe(2)
    expect(closed[0]!.notes[0]!.midi).not.toBe(closed[0]!.notes[1]!.midi)
  })

  it('flush emits an open phrase', () => {
    const closed: unknown[] = []
    const seg = createJamPhraseSegmenter({
      onPhraseClosed: () => closed.push(1),
    })
    seg.push(readingHz(440), 0, 0)
    seg.push(readingHz(493.88), 200, 200)
    seg.flush(500)
    expect(closed.length).toBe(1)
  })

  it('reset clears state without callback', () => {
    const onClosed = vi.fn()
    const seg = createJamPhraseSegmenter({ onPhraseClosed: onClosed })
    seg.push(readingHz(440), 0, 0)
    seg.reset()
    seg.push(silent(), 600, 600)
    expect(onClosed).not.toHaveBeenCalled()
  })
})
