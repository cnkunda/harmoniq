/**
 * Pure Riff DNA aggregation from local session history (commit 74).
 * No I/O — safe for unit tests.
 */

import type { NoteResultLabel } from '@/src/session/noteAccuracyBeats'

export const DNA_MIN_SESSIONS = 3

const PC_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const

export type HarmoniqDnaCapture = {
  note_target_midis?: number[]
  note_results?: NoteResultLabel[]
  note_target_cells?: Array<{ row: number; fret: number } | null>
  bpm_drift_ms?: number
  bpm_drift_sample_count?: number
}

export type PlayerDNA = {
  pitch_class_bias: number[]
  position_bias: number[]
  timing_feel: 'ahead' | 'behind' | 'centered'
  technique_frequency: Record<string, number>
  firstRecordedDate: string | null
  /** Play Review rows + Jam snapshots (licks do not increment). */
  eligibleSessionCount: number
}

export type DnaPlaySessionInput = {
  date: string
  review_snapshot: string | null
  nodes_targeted: string[]
}

export type DnaJamInput = {
  date: string
  pitch_class_weight_map: Record<string, number>
  position_weight_map: Record<string, number>
  recurring_gestures: string[]
}

export type DnaLickInput = {
  date_saved: string
  position: string | null
  technique_tags: string[]
}

function zero12(): number[] {
  return Array.from({ length: 12 }, () => 0)
}

function normalizeMax(vec: number[]): number[] {
  const m = Math.max(...vec, 1e-9)
  return vec.map((x) => x / m)
}

function parseCapture(raw: string | null | undefined): HarmoniqDnaCapture | null {
  if (raw == null || raw.trim() === '') return null
  try {
    const o = JSON.parse(raw) as { harmoniq_dna_capture?: unknown }
    const c = o.harmoniq_dna_capture
    if (!c || typeof c !== 'object') return null
    return c as HarmoniqDnaCapture
  } catch {
    return null
  }
}

function pitchClassIndexFromKey(key: string): number | null {
  const k = key.trim()
  if (!k) return null
  const rest = k.startsWith('pc_') ? k.slice(3) : k
  const idx = (PC_NAMES as readonly string[]).indexOf(rest)
  return idx >= 0 ? idx : null
}

function addJamPitchMap(hist: number[], m: Record<string, number>): void {
  for (const [key, w] of Object.entries(m)) {
    const idx = pitchClassIndexFromKey(key)
    if (idx == null || !Number.isFinite(w) || w <= 0) continue
    hist[idx] += w
  }
}

function addJamPositionMap(hist: number[], m: Record<string, number>): void {
  for (const [key, w] of Object.entries(m)) {
    if (!Number.isFinite(w) || w <= 0) continue
    const pc = pitchClassIndexFromKey(key)
    if (pc != null) {
      hist[pc] += w
      continue
    }
    const n = parseInt(key.replace(/\D/g, ''), 10)
    if (!Number.isFinite(n)) continue
    hist[fretToZone(n)] += w
  }
}

function fretToZone(fret: number): number {
  const f = Math.round(fret)
  return Math.min(11, Math.max(0, Math.floor(f / 2)))
}

function lickPositionToZone(position: string | null): number | null {
  if (position == null || !position.trim()) return null
  const m = position.match(/(\d+)/)
  if (!m) return null
  const n = parseInt(m[1]!, 10)
  if (!Number.isFinite(n)) return null
  return fretToZone(Math.min(24, Math.max(0, n)))
}

function timingFromCaptureAndScore(
  capture: HarmoniqDnaCapture | null,
  rushingScore: number | null,
  p50ms: number | null,
): number | null {
  if (capture && capture.bpm_drift_sample_count && capture.bpm_drift_sample_count > 0) {
    const d = capture.bpm_drift_ms
    if (typeof d === 'number' && Number.isFinite(d)) return d
  }
  if (typeof p50ms === 'number' && Number.isFinite(p50ms)) return p50ms
  if (typeof rushingScore === 'number' && Number.isFinite(rushingScore)) {
    return (0.5 - Math.max(0, Math.min(1, rushingScore))) * 90
  }
  return null
}

function classifyTimingFeel(avgMs: number | null): 'ahead' | 'behind' | 'centered' {
  if (avgMs == null || !Number.isFinite(avgMs)) return 'centered'
  if (avgMs > 12) return 'ahead'
  if (avgMs < -12) return 'behind'
  return 'centered'
}

export function computePlayerDNA(input: {
  sessions: DnaPlaySessionInput[]
  jams: DnaJamInput[]
  licks: DnaLickInput[]
}): PlayerDNA {
  const pitchHist = zero12()
  const posHist = zero12()
  const technique: Record<string, number> = {}
  const dates: string[] = []
  const timingSamples: number[] = []
  const timingWeights: number[] = []

  for (const s of input.sessions) {
    dates.push(s.date)
    for (const id of s.nodes_targeted) {
      const k = id.trim()
      if (k) technique[k] = (technique[k] ?? 0) + 1
    }

    const raw = s.review_snapshot
    let rushing: number | null = null
    let p50: number | null = null
    if (raw && raw.trim()) {
      try {
        const o = JSON.parse(raw) as {
          rushing_score?: number
          diagnostics?: { timing_residual_p50_ms?: number }
        }
        if (typeof o.rushing_score === 'number' && Number.isFinite(o.rushing_score)) rushing = o.rushing_score
        const d = o.diagnostics
        if (d && typeof d.timing_residual_p50_ms === 'number' && Number.isFinite(d.timing_residual_p50_ms)) {
          p50 = d.timing_residual_p50_ms
        }
      } catch {
        /* ignore */
      }
    }

    const cap = parseCapture(raw)
    const drift = timingFromCaptureAndScore(cap, rushing, p50)
    const w = cap?.bpm_drift_sample_count && cap.bpm_drift_sample_count > 0 ? cap.bpm_drift_sample_count : 1
    if (drift != null) {
      timingSamples.push(drift)
      timingWeights.push(w)
    }

    const midis = cap?.note_target_midis
    if (midis && midis.length > 0) {
      const results = cap.note_results
      for (let i = 0; i < midis.length; i += 1) {
        const res = results?.[i]
        if (res === 'ignored') continue
        const m = midis[i]
        if (typeof m !== 'number' || !Number.isFinite(m)) continue
        const pc = Math.round(m) % 12
        if (pc >= 0 && pc < 12) pitchHist[pc] += 1

        const cell = cap.note_target_cells?.[i]
        if (cell && typeof cell.fret === 'number' && Number.isFinite(cell.fret)) {
          posHist[fretToZone(cell.fret)] += 1
        }
      }
    }
  }

  for (const j of input.jams) {
    dates.push(j.date)
    addJamPitchMap(pitchHist, j.pitch_class_weight_map)
    addJamPositionMap(posHist, j.position_weight_map)
    for (const g of j.recurring_gestures) {
      const k = g.trim().toLowerCase()
      if (k) technique[`jam:${k}`] = (technique[`jam:${k}`] ?? 0) + 1
    }
  }

  for (const l of input.licks) {
    dates.push(l.date_saved)
    const z = lickPositionToZone(l.position)
    if (z != null) posHist[z] += 1
    for (const t of l.technique_tags) {
      const k = t.trim()
      if (k) technique[`lick:${k}`] = (technique[`lick:${k}`] ?? 0) + 1
    }
  }

  let timingAvg: number | null = null
  if (timingSamples.length > 0) {
    let sumW = 0
    let sum = 0
    for (let i = 0; i < timingSamples.length; i += 1) {
      const wi = timingWeights[i] ?? 1
      sum += timingSamples[i]! * wi
      sumW += wi
    }
    timingAvg = sumW > 0 ? sum / sumW : null
  }

  const eligibleSessionCount = input.sessions.length + input.jams.length
  let firstRecordedDate: string | null = null
  if (dates.length > 0) {
    firstRecordedDate = [...dates].sort((a, b) => a.localeCompare(b))[0] ?? null
  }

  return {
    pitch_class_bias: normalizeMax(pitchHist),
    position_bias: normalizeMax(posHist),
    timing_feel: classifyTimingFeel(timingAvg),
    technique_frequency: technique,
    firstRecordedDate,
    eligibleSessionCount,
  }
}
