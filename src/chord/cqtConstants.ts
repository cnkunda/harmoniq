/**
 * CQT feature constants — mirrors backend/app/cqt_constants.py.
 *
 * Single source of truth for all CQT extraction parameters used across
 * training, extraction, and on-device inference.
 */

/** CQT frequency resolution: 24 bins per octave. */
export const BINS_PER_OCTAVE = 24

/** Number of octaves covered (guitar range E2-E5 + harmonics). */
export const NUM_OCTAVES = 6

/** Total CQT frequency bins: 24 × 6 = 144. */
export const CHROMA_BINS = BINS_PER_OCTAVE * NUM_OCTAVES

/** No separate bass channel in the current architecture. */
export const BASS_BINS = 0

/** Total feature dimension (equals CHROMA_BINS when BASS_BINS = 0). */
export const FEATURE_DIM = CHROMA_BINS

/** Temporal window size in frames (128 frames × 0.1s = 12.8s context). */
export const WINDOW = 128

/** Hop size in frames (50% overlap between windows). */
export const HOP_FRAMES = 64

/** Audio sample rate in Hz. */
export const TARGET_SR = 44100

/** Hop size in seconds (0.1s per CQT frame). */
export const HOP_SEC = 0.1

/** Hop length in samples at TARGET_SR (44100 × 0.1 = 4410). */
export const HOP_LENGTH = TARGET_SR * HOP_SEC
