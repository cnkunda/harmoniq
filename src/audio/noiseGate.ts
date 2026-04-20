/**
 * Ambient noise calibration → RMS gate used alongside dynamic ghost detection (Commit 62).
 * Threshold = ambient RMS × 10^(6/20) (“RMS floor + 6 dB headroom”).
 */

/** Headroom above measured ambient RMS when forming the gate threshold (PRIORITIES §62). */
export const NOISE_GATE_HEADROOM_DB = 6

export function linearRatioFromDb(db: number): number {
  return Math.pow(10, db / 20)
}

export function ambientRmsAverage(samples: readonly number[]): number {
  if (samples.length === 0) return 0
  let sum = 0
  for (const s of samples) {
    if (Number.isFinite(s)) sum += s
  }
  return sum / samples.length
}

/** RMS gate threshold from a batch of ambient samples (linear amplitude). */
export function noiseGateThresholdFromAmbientSamples(samples: readonly number[]): number {
  const avg = ambientRmsAverage(samples)
  return avg * linearRatioFromDb(NOISE_GATE_HEADROOM_DB)
}

/**
 * Effective minimum RMS to treat Play capture signal as “real note” vs silence/ghost noise.
 * Combines dynamic ghost threshold (Commit 49) with calibrated ambient floor (Commit 62).
 */
export function effectiveRmsSignalGate(dynamicGhostThreshold: number, calibratedGateRms: number | null | undefined): number {
  const dyn = typeof dynamicGhostThreshold === 'number' && Number.isFinite(dynamicGhostThreshold) ? dynamicGhostThreshold : 0
  const cal =
    typeof calibratedGateRms === 'number' && Number.isFinite(calibratedGateRms) && calibratedGateRms > 0 ? calibratedGateRms : 0
  return Math.max(dyn, cal)
}
