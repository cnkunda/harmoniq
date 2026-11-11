/** Pure count-in math (kept free of RN imports for unit tests). */

export function countInBeatPeriodMs(bpm: number): number {
  const safe = Number.isFinite(bpm) && bpm > 0 ? bpm : 96
  return (60 / safe) * 1000
}

/** 1-based beat index; every bar starts on a downbeat click. */
export function isCountInDownbeat(beatIndex: number, beatsPerBar = 4): boolean {
  const perBar = Math.max(1, Math.round(beatsPerBar))
  return (Math.max(1, Math.round(beatIndex)) - 1) % perBar === 0
}
