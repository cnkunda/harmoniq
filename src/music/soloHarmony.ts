import type {
  BarScope,
  ChordToneAnalysis,
  HarmonizedSoloNote,
  HarmonizedSoloNotes,
} from '@/src/types/soloHarmony'

const CHORD_TONE_TYPES = ['chord_tone', 'tension', 'chromatic', 'pedal'] as const

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function finiteNumberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}

function parseChordToneAnalysis(raw: unknown): ChordToneAnalysis | null {
  if (!isRecord(raw)) return null
  const type = raw.chord_tone_type
  if (typeof type !== 'string' || !(CHORD_TONE_TYPES as readonly string[]).includes(type)) return null
  const name = raw.scale_degree_name
  if (typeof name !== 'string') return null
  const distance = finiteNumberOrNull(raw.semitone_distance)
  if (distance === null) return null
  const degree = finiteNumberOrNull(raw.scale_degree)
  return {
    scale_degree: degree,
    scale_degree_name: name,
    chord_tone_type: type as ChordToneAnalysis['chord_tone_type'],
    semitone_distance: distance,
  }
}

function parseHarmonizedSoloNote(raw: unknown): HarmonizedSoloNote | null {
  if (!isRecord(raw)) return null
  const startTime = finiteNumberOrNull(raw.start_time)
  const pitch = finiteNumberOrNull(raw.pitch)
  if (startTime === null || pitch === null) return null
  const analysis = raw.chord_analysis == null ? null : parseChordToneAnalysis(raw.chord_analysis)
  return {
    start_time: startTime,
    duration: finiteNumberOrNull(raw.duration) ?? 0,
    pitch,
    velocity: finiteNumberOrNull(raw.velocity) ?? 0,
    chord: typeof raw.chord === 'string' ? raw.chord : null,
    chord_analysis: analysis,
  }
}

/**
 * Tolerant runtime parse of a backend `HarmonizedSoloNotes` payload.
 *
 * Returns null when the payload is not an object or `notes` is not an array.
 * Malformed note entries are dropped; missing aggregates normalize to 0.
 * A valid payload with an empty `notes` array stays distinct from null.
 */
export function parseHarmonizedSolo(raw: unknown): HarmonizedSoloNotes | null {
  if (!isRecord(raw) || !Array.isArray(raw.notes)) return null
  const notes: HarmonizedSoloNote[] = []
  for (const entry of raw.notes) {
    const note = parseHarmonizedSoloNote(entry)
    if (note) notes.push(note)
  }
  return {
    notes,
    note_count: finiteNumberOrNull(raw.note_count) ?? notes.length,
    chord_tone_pct: clamp01(finiteNumberOrNull(raw.chord_tone_pct) ?? 0),
    tension_note_pct: clamp01(finiteNumberOrNull(raw.tension_note_pct) ?? 0),
    chromatic_pct: clamp01(finiteNumberOrNull(raw.chromatic_pct) ?? 0),
  }
}

function parseBarScope(raw: unknown, index: number): BarScope | null {
  if (!isRecord(raw)) return null
  const startTime = finiteNumberOrNull(raw.start_time)
  const endTime = finiteNumberOrNull(raw.end_time)
  if (startTime === null || endTime === null) return null
  return {
    bar_index: finiteNumberOrNull(raw.bar_index) ?? index,
    start_time: startTime,
    end_time: endTime,
    chord: typeof raw.chord === 'string' ? raw.chord : null,
    suggested_scales: Array.isArray(raw.suggested_scales)
      ? raw.suggested_scales.filter((s): s is string => typeof s === 'string')
      : [],
    primary_position: typeof raw.primary_position === 'string' ? raw.primary_position : null,
    notes: Array.isArray(raw.notes)
      ? raw.notes.filter((n): n is number => typeof n === 'number' && Number.isInteger(n) && n >= 0)
      : [],
  }
}

/**
 * Tolerant runtime parse of a backend `per_bar_analysis` payload.
 *
 * Returns null when the payload is not an array; malformed bar entries are
 * dropped and malformed fields normalize to empty/null.
 */
export function parsePerBarAnalysis(raw: unknown): BarScope[] | null {
  if (!Array.isArray(raw)) return null
  const bars: BarScope[] = []
  for (let i = 0; i < raw.length; i += 1) {
    const bar = parseBarScope(raw[i], i)
    if (bar) bars.push(bar)
  }
  return bars
}

/**
 * Resolve the BarScope covering `timeSec`, by time range only.
 *
 * Never match by array index: backend `BarScope.bar_index` is enumerated from
 * raw downbeats while `lesson.bar_timestamps` prepends 0.0 when the first
 * downbeat starts late (analyze_audio.py), so the two can be off by one.
 */
export function barScopeForTime(
  perBar: BarScope[] | null | undefined,
  timeSec: number,
): BarScope | null {
  if (!perBar || !Number.isFinite(timeSec)) return null
  for (const bar of perBar) {
    if (bar.start_time <= timeSec && timeSec < bar.end_time) return bar
  }
  return null
}

/**
 * Find the harmonized analysis for a tapped note.
 *
 * Order: bar-scoped index scan first (the backend's own note segmentation,
 * repeated pitches tie-break to the earliest onset), then a pitch-only
 * fallback — an unambiguous single match, or the onset nearest `timeSec`
 * when a playback time is known. Returns null when nothing matches, which
 * lets callers keep their existing client-side chord-tone computation.
 */
export function findHarmonizedNoteForSelection(
  harmonized: HarmonizedSoloNotes | null | undefined,
  perBar: BarScope[] | null | undefined,
  selection: { midi?: number | null; timeSec?: number | null },
): HarmonizedSoloNote | null {
  const midi = selection.midi
  if (!harmonized || harmonized.notes.length === 0 || !Number.isFinite(midi)) return null
  const midiValue = midi as number

  const timeSec = selection.timeSec
  const hasTime = typeof timeSec === 'number' && Number.isFinite(timeSec)
  if (hasTime) {
    const bar = barScopeForTime(perBar, timeSec)
    if (bar) {
      let best: HarmonizedSoloNote | null = null
      for (const idx of bar.notes) {
        const note = harmonized.notes[idx]
        if (!note || note.pitch !== midiValue) continue
        if (!best || note.start_time < best.start_time) best = note
      }
      if (best) return best
    }
  }

  const matches = harmonized.notes.filter((note) => note.pitch === midiValue)
  if (matches.length === 1) return matches[0] ?? null
  if (matches.length > 1 && hasTime) {
    let nearest: HarmonizedSoloNote | null = null
    let nearestDistance = Infinity
    for (const note of matches) {
      const distance = Math.abs(note.start_time - (timeSec as number))
      if (distance < nearestDistance) {
        nearestDistance = distance
        nearest = note
      }
    }
    return nearest
  }
  return null
}

/**
 * Whole-percent view of a harmonized solo's role fractions, for display.
 */
export function formatHarmonyPercents(harmonized: HarmonizedSoloNotes): {
  chordTone: number
  tension: number
  chromatic: number
} {
  return {
    chordTone: Math.round(harmonized.chord_tone_pct * 100),
    tension: Math.round(harmonized.tension_note_pct * 100),
    chromatic: Math.round(harmonized.chromatic_pct * 100),
  }
}
