import {
  barIndexAtOrBeforeTime,
  barRangeToSeconds,
  clampBarLoopRange,
  pickLowestNumericBarIndex,
} from '@/src/music/barLoopBounds'

export type SlowLoopDerived = {
  startSec: number
  endSec: number
  label: string
  source: string
  startBarIndex: number
  endBarIndexExclusive: number
}

function asNumber(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const n = Number.parseFloat(v)
    if (Number.isFinite(n)) return n
  }
  return null
}

function singleBarWindow(
  barTimestamps: readonly number[],
  barIndex: number,
  beatSec: number,
): Pick<SlowLoopDerived, 'startSec' | 'endSec' | 'startBarIndex' | 'endBarIndexExclusive'> | null {
  const r = barRangeToSeconds(barTimestamps, barIndex, barIndex + 1, beatSec)
  if (!r) return null
  return {
    startSec: r.startSec,
    endSec: r.endSec,
    startBarIndex: barIndex,
    endBarIndexExclusive: barIndex + 1,
  }
}

function firstChorusWindow(
  sections: Array<Record<string, unknown>>,
  barTimestamps: readonly number[],
  beatSec: number,
): SlowLoopDerived | null {
  const chorusIndex = sections.findIndex((s) => {
    const raw = typeof s.label === 'string' ? s.label : ''
    return raw.toLowerCase().includes('chorus')
  })
  if (chorusIndex < 0) return null
  const here = sections[chorusIndex]
  const startT =
    typeof here === 'object' && here
      ? (asNumber((here as Record<string, unknown>).start_time_seconds) ??
        asNumber((here as Record<string, unknown>).start_s) ??
        asNumber((here as Record<string, unknown>).startTimeSeconds))
      : null
  if (startT == null) return null
  const nextSec =
    chorusIndex + 1 < sections.length
      ? (() => {
          const n = sections[chorusIndex + 1]
          if (!n || typeof n !== 'object') return null
          const o = n as Record<string, unknown>
          return asNumber(o.start_time_seconds) ?? asNumber(o.start_s) ?? asNumber(o.startTimeSeconds)
        })()
      : null
  const span = Math.max(0.6, beatSec * 4)
  const endWall = nextSec != null && nextSec > startT ? Math.min(nextSec, startT + span) : startT + span
  if (barTimestamps.length > 0) {
    const startBar = barIndexAtOrBeforeTime(barTimestamps, startT)
    let endEx = barTimestamps.length
    for (let i = startBar + 1; i < barTimestamps.length; i += 1) {
      if (barTimestamps[i]! >= endWall) {
        endEx = i
        break
      }
    }
    endEx = Math.max(startBar + 1, endEx)
    const { startBarIndex, endBarIndexExclusive } = clampBarLoopRange(startBar, endEx, barTimestamps.length)
    const r = barRangeToSeconds(barTimestamps, startBarIndex, endBarIndexExclusive, beatSec)
    if (r) {
      return {
        ...r,
        label: 'First chorus',
        source: 'chorus',
        startBarIndex,
        endBarIndexExclusive,
      }
    }
  }
  return {
    startSec: startT,
    endSec: endWall,
    label: 'First chorus',
    source: 'chorus',
    startBarIndex: 0,
    endBarIndexExclusive: 1,
  }
}

const CONFIDENCE_BAR_ARRAY_KEYS = [
  'confidence_by_bar',
  'bar_confidence',
  'transcription_confidence_by_bar',
  'section_confidence_by_bar',
] as const

export function deriveSlowLoopRegion(
  section: Record<string, unknown> | undefined,
  sections: Array<Record<string, unknown>>,
  barTimestamps: number[],
  tempo: number | null | undefined,
): SlowLoopDerived | null {
  const beatSec = tempo && tempo > 0 ? 60 / tempo : 0.5
  const sec = section ?? {}
  const bars = barTimestamps

  // Explicit multi-bar ranges from analysis first; then lowest-confidence bar when arrays exist (G3 / PRIORITIES); then single-bar hints.
  const rangeKeys: Array<[string, string]> = [
    ['loop_start_bar', 'loop_end_bar'],
    ['loopStartBar', 'loopEndBar'],
    ['hardest_start_bar', 'hardest_end_bar'],
    ['hardestStartBar', 'hardestEndBar'],
  ]
  for (const [a, b] of rangeKeys) {
    const startBar = asNumber(sec[a])
    const endBar = asNumber(sec[b])
    if (startBar != null && bars.length > 0) {
      const start = Math.floor(startBar)
      const endEx = Math.max(start + 1, Math.floor(endBar ?? start + 1))
      const clamped = clampBarLoopRange(start, endEx, bars.length)
      const r2 = barRangeToSeconds(bars, clamped.startBarIndex, clamped.endBarIndexExclusive, beatSec)
      if (r2) {
        return {
          ...r2,
          label: `Bars ${clamped.startBarIndex + 1}-${clamped.endBarIndexExclusive}`,
          source: `section.${a}/${b}`,
          startBarIndex: clamped.startBarIndex,
          endBarIndexExclusive: clamped.endBarIndexExclusive,
        }
      }
    }
  }

  for (const key of CONFIDENCE_BAR_ARRAY_KEYS) {
    const raw = sec[key]
    if (!Array.isArray(raw) || raw.length === 0 || bars.length === 0) continue
    const idx = pickLowestNumericBarIndex(raw)
    if (idx == null) continue
    const w = singleBarWindow(bars, idx, beatSec)
    if (w) {
      return {
        ...w,
        label: `Bar ${idx + 1} (low confidence)`,
        source: `section.${key}`,
      }
    }
  }

  const barKeys = ['hardest_bar_index', 'hardestBarIndex', 'hardest_bar', 'hardestBar', 'loop_bar', 'loopBar']
  for (const key of barKeys) {
    const n = asNumber(sec[key])
    if (n != null) {
      const bi = Math.floor(n)
      const w = singleBarWindow(bars, bi, beatSec)
      if (w) {
        return {
          ...w,
          label: `Bar ${bi + 1}`,
          source: `section.${key}`,
        }
      }
    }
  }

  const chorus = firstChorusWindow(sections, bars, beatSec)
  if (chorus) return chorus

  const st =
    sec.start_time_seconds ?? sec.start_s ?? sec.startTimeSeconds
  const currentStart = typeof st === 'number' && Number.isFinite(st) ? Math.max(0, st) : null
  if (currentStart != null) {
    if (bars.length > 0) {
      const startBar = barIndexAtOrBeforeTime(bars, currentStart)
      const endEx = Math.min(bars.length, startBar + 2)
      const clamped = clampBarLoopRange(startBar, endEx, bars.length)
      const r = barRangeToSeconds(bars, clamped.startBarIndex, clamped.endBarIndexExclusive, beatSec)
      if (r) {
        return {
          ...r,
          label: 'Current section start',
          source: 'section.start_time_seconds fallback',
          startBarIndex: clamped.startBarIndex,
          endBarIndexExclusive: clamped.endBarIndexExclusive,
        }
      }
    }
    return {
      startSec: currentStart,
      endSec: currentStart + Math.max(0.6, beatSec * 4),
      label: 'Current section start',
      source: 'section.start_time_seconds fallback',
      startBarIndex: 0,
      endBarIndexExclusive: Math.min(2, Math.max(1, bars.length || 2)),
    }
  }

  if (bars.length > 0) {
    const w = singleBarWindow(bars, 0, beatSec)
    if (w) {
      return {
        ...w,
        label: 'Bar 1',
        source: 'bar_timestamps[0] fallback',
      }
    }
  }

  return null
}
