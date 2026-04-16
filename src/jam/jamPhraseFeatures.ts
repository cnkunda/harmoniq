import type { JamPhrase } from '@/src/jam/jamPhraseSegmenter'

export type JamPhraseContour = 'rising' | 'falling' | 'static' | 'arch' | 'mixed'

export type JamPhraseFeatures = {
  durationSec: number
  notesPerSecond: number
  uniquePitchClasses: number
  midiSpan: number
  contour: JamPhraseContour
  /** Signed: negative → ahead of grid (rushing), positive → behind (dragging). */
  meanBeatOffsetSec: number | null
  beatOffsetVarianceSec2: number | null
  noteCount: number
}

function signedBeatOffsetSec(absoluteSec: number, beatPeriodSec: number): number {
  if (!Number.isFinite(absoluteSec) || !Number.isFinite(beatPeriodSec) || beatPeriodSec <= 0) return 0
  let m = absoluteSec % beatPeriodSec
  if (m < 0) m += beatPeriodSec
  const half = beatPeriodSec / 2
  if (m > half) m -= beatPeriodSec
  return m
}

function classifyContour(midis: number[]): JamPhraseContour {
  if (midis.length < 2) return 'mixed'
  const first = midis[0]!
  const last = midis[midis.length - 1]!
  let min = first
  let max = first
  let maxI = 0
  let minI = 0
  for (let i = 0; i < midis.length; i += 1) {
    const v = midis[i]!
    if (v < min) {
      min = v
      minI = i
    }
    if (v > max) {
      max = v
      maxI = i
    }
  }
  const interiorHasMax = maxI > 0 && maxI < midis.length - 1
  const interiorHasMin = minI > 0 && minI < midis.length - 1
  if (interiorHasMax && last < max - 1 && first < max - 1) return 'arch'
  if (interiorHasMin && last > min + 1 && first > min + 1) return 'mixed'
  if (last - first >= 2) return 'rising'
  if (first - last >= 2) return 'falling'
  if (Math.abs(last - first) <= 1 && max - min <= 2) return 'static'
  return 'mixed'
}

/**
 * Derive musical-shape features from a closed phrase. Beat stats are omitted unless
 * every note carries `backingPosMs` and `bpm` is provided (loop-relative grid).
 */
export function phraseToFeatures(phrase: JamPhrase, bpm: number | null | undefined): JamPhraseFeatures {
  const notes = phrase.notes
  const noteCount = notes.length
  const durationMs = Math.max(0, phrase.endTime - phrase.startTime)
  const durationSec = durationMs / 1000
  const midis = notes.map((n) => n.midi)
  const pcs = midis.map((m) => ((m % 12) + 12) % 12)
  const uniquePitchClasses = new Set(pcs).size
  const midiSpan = midis.length > 0 ? Math.max(...midis) - Math.min(...midis) : 0
  const notesPerSecond = durationSec > 0.05 ? noteCount / durationSec : 0
  const contour = classifyContour(midis)

  let meanBeatOffsetSec: number | null = null
  let beatOffsetVarianceSec2: number | null = null

  const beatPeriodSec =
    typeof bpm === 'number' && Number.isFinite(bpm) && bpm > 0 ? 60 / Math.min(220, Math.max(48, bpm)) : null

  if (beatPeriodSec != null && notes.every((n) => typeof n.backingPosMs === 'number')) {
    const offsets: number[] = []
    for (const n of notes) {
      const sec = (n.backingPosMs as number) / 1000
      offsets.push(signedBeatOffsetSec(sec, beatPeriodSec))
    }
    const mean = offsets.reduce((a, b) => a + b, 0) / offsets.length
    meanBeatOffsetSec = mean
    beatOffsetVarianceSec2 =
      offsets.length > 1
        ? offsets.reduce((s, o) => s + (o - mean) * (o - mean), 0) / (offsets.length - 1)
        : 0
  }

  return {
    durationSec,
    notesPerSecond,
    uniquePitchClasses,
    midiSpan,
    contour,
    meanBeatOffsetSec,
    beatOffsetVarianceSec2,
    noteCount,
  }
}
