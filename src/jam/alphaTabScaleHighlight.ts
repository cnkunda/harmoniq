/**
 * AlphaTab 1.6.x — tint tab numbers and standard note heads for pitch classes in the detected scale.
 * Used from `AlphaTabWeb.web.tsx` (DOM). Native uses the same logic in `assets/alphatab-harness/index.html`.
 */

const TINT_HEX = '#6EC88C'

type UnknownRecord = Record<string, unknown>

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : []
}

function noteMidi(note: UnknownRecord): number | null {
  if (typeof note.realValue === 'number' && Number.isFinite(note.realValue)) return Math.round(note.realValue)
  if (typeof note.midi === 'number' && Number.isFinite(note.midi)) return Math.round(note.midi)
  return null
}

function pitchClassSetFromRootIntervals(rootMidi: number, intervals: readonly number[]): Set<number> {
  const rootPc = ((Math.round(rootMidi) % 12) + 12) % 12
  const set = new Set<number>()
  for (const off of intervals) {
    if (!Number.isFinite(off)) continue
    set.add((((rootPc + off) % 12) + 12) % 12)
  }
  return set
}

function forEachNoteInScore(score: UnknownRecord, fn: (note: UnknownRecord) => void): void {
  for (const track of asArray(score.tracks)) {
    const tr = track as UnknownRecord
    for (const bar of asArray(tr.bars)) {
      const b = bar as UnknownRecord
      for (const voice of asArray(b.voices)) {
        const v = voice as UnknownRecord
        for (const beat of asArray(v.beats)) {
          const be = beat as UnknownRecord
          for (const note of asArray(be.notes)) {
            fn(note as UnknownRecord)
          }
        }
      }
    }
  }
}

function triggerRender(api: UnknownRecord): void {
  const renderer = api.renderer as UnknownRecord | undefined
  const render = renderer && typeof renderer.render === 'function' ? (renderer.render as () => void) : null
  try {
    render?.()
  } catch {
    /* AlphaTab may throw if not ready */
  }
  try {
    if (typeof api.updateSettings === 'function') {
      ;(api.updateSettings as () => void)()
    }
  } catch {
    /* optional */
  }
}

export function applyScaleDegreeHighlight(
  api: UnknownRecord | null | undefined,
  alphaTabGlobal: UnknownRecord | null | undefined,
  rootMidi: number,
  intervals: readonly number[],
): void {
  if (!api || !alphaTabGlobal) return
  const score = api.score as UnknownRecord | undefined
  const model = alphaTabGlobal.model as UnknownRecord | undefined
  if (!score || !model) return

  const NoteStyle = model.NoteStyle as (new () => UnknownRecord) | undefined
  const NoteSubElement = model.NoteSubElement as UnknownRecord | undefined
  const Color = model.Color as { fromJson?: (s: string) => unknown } | undefined
  if (!NoteStyle || !NoteSubElement || !Color || typeof Color.fromJson !== 'function') return

  const tabEl = NoteSubElement.GuitarTabFretNumber
  const headEl = NoteSubElement.StandardNotationNoteHead
  if (tabEl == null || headEl == null) return

  const tint = Color.fromJson(TINT_HEX)
  const targets = pitchClassSetFromRootIntervals(rootMidi, intervals)
  if (targets.size === 0) return

  forEachNoteInScore(score, (note) => {
    const midi = noteMidi(note)
    if (midi == null) return
    const pc = ((midi % 12) + 12) % 12
    if (!targets.has(pc)) return
    const style = new NoteStyle() as UnknownRecord
    const colors = style.colors as { set?: (k: unknown, c: unknown) => void } | undefined
    if (!colors || typeof colors.set !== 'function') return
    colors.set(tabEl, tint)
    colors.set(headEl, tint)
    note.style = style
  })

  triggerRender(api)
}

export function clearScaleDegreeHighlight(api: UnknownRecord | null | undefined): void {
  if (!api) return
  const score = api.score as UnknownRecord | undefined
  if (!score) return
  forEachNoteInScore(score, (note) => {
    note.style = null
  })
  triggerRender(api)
}
