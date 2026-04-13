/**
 * Pitch practice tuning — values need calibration against real performances and devices.
 * Phrase-level adaptation is approximated using consecutive-beat and sliding-window heuristics
 * (no explicit phrase boundaries in Play).
 */

/** Initial cents band for “close” / adapted tolerance before adaptation runs. */
export const CENTS_TOLERANCE = 20

// --- Ghost note dynamic amplitude (calibrate against real input levels / mics)
/** Samples with timestamps kept for recent RMS peak (ms). */
export const GHOST_RMS_WINDOW_MS = 600
/**
 * Threshold RMS = peak_in_window × 10^(−dB/20). Quieter pick attacks sit below this vs recent peak.
 * Calibrate with blues/soul ghost-note takes so real notes still score.
 */
export const GHOST_DB_BELOW_PEAK = 18
/** Ignore noise floor when peak is near silence. */
export const GHOST_RMS_MIN_FLOOR = 0.00012

// --- Vibrato (guitar bend vibrato can be wider / less regular than classical targets)
export const VIBRATO_RATE_MIN_HZ = 4
export const VIBRATO_RATE_MAX_HZ = 8
/** Peak-to-peak cents; avoids false negatives on shallow warble. */
export const VIBRATO_DEPTH_CENTS_PEAK_TO_PEAK = 30
export const VIBRATO_MIN_DURATION_MS = 200

export const AUTO_LOOP_MISS_THRESHOLD = 2

// --- Difficulty adaptation (calibrate against real users before shipping)
export const ADAPT_TIGHTEN_THRESHOLD = 3
/** Widen when miss count in the sliding window reaches this (calibrate with ADAPT_MISS_WINDOW_BEATS). */
export const ADAPT_WIDEN_THRESHOLD = 3
export const ADAPT_STEP_CENTS = 2
/** 5¢ is near perceptual limen for many players in context — too punishing as a floor. */
export const ADAPT_FLOOR_CENTS = 15
export const ADAPT_CEILING_CENTS = 25

/** Last N closed beats used to detect “rough” windows for widening. */
export const ADAPT_MISS_WINDOW_BEATS = 6

export const BPM_DRIFT_THRESHOLD_MS = 30
export const BPM_DRIFT_NOTE_MINIMUM = 4

/** Inner “direct hit” tier: min of this cap and adapted × ratio (see noteAccuracyBeats). */
export const HIT_INNER_MAX_CENTS = 15
export const HIT_VS_ADAPTED_RATIO = 0.55

/** Pitch contour sample interval (ms) during Play. */
export const CONTOUR_SAMPLE_MS = 30
