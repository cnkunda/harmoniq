export const DB_NAME = 'harmoniq_v1.db'

export const MIGRATION_V1 = `
CREATE TABLE IF NOT EXISTS skill_nodes (
  id TEXT PRIMARY KEY,
  label TEXT,
  score REAL DEFAULT 0.0,
  sessions_count INTEGER DEFAULT 0,
  last_session_date TEXT,
  easiness_factor REAL DEFAULT 2.5,
  interval_days INTEGER DEFAULT 1,
  next_review_date TEXT,
  sm2_repetitions INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  song_title TEXT,
  artist TEXT,
  section_label TEXT,
  date TEXT,
  coach_review TEXT,
  pitch_accuracy REAL,
  phrasing_score REAL,
  nodes_targeted TEXT
);

CREATE TABLE IF NOT EXISTS licks (
  id TEXT PRIMARY KEY,
  song_title TEXT,
  artist TEXT,
  key TEXT,
  scale TEXT,
  position TEXT,
  tab_gp5_base64 TEXT,
  audio_segment_path TEXT,
  coach_oneliner TEXT,
  technique_tags TEXT,
  user_annotations TEXT,
  date_saved TEXT
);

CREATE TABLE IF NOT EXISTS jam_snapshots (
  id TEXT PRIMARY KEY,
  date TEXT,
  duration_seconds INTEGER,
  scale_position_map TEXT,
  recurring_gestures TEXT,
  coach_summary TEXT
);
`

export const MIGRATION_TABLE_SQL = `
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);
`

/** v3: app key-value (onboarding flag, future prefs). */
export const MIGRATION_V3_APP_PREFS = `
CREATE TABLE IF NOT EXISTS app_prefs (
  key TEXT PRIMARY KEY NOT NULL,
  value TEXT NOT NULL
);
`

/** v4: persisted review payload + optional on-disk waveform paths (PRIORITIES §35). */
export const MIGRATION_V4_SESSIONS_REVIEW = [
  'ALTER TABLE sessions ADD COLUMN review_snapshot TEXT',
  'ALTER TABLE sessions ADD COLUMN waveform_user_path TEXT',
  'ALTER TABLE sessions ADD COLUMN waveform_ref_path TEXT',
] as const

export const PREF_ONBOARDING_COMPLETE = 'onboarding_complete'

/** Prefer skeleton (or alt) tab when `LessonJSON.transcription_confidence` is low (PRIORITIES §37). */
export const PREF_PREFER_SIMPLER_TABS = 'prefer_simpler_tabs'
/** A4 reference in Hz (future tuner / playback). */
export const PREF_STANDARD_TUNING_HZ = 'standard_tuning_hz'
/** Short free-text style focus for coach context later. */
export const PREF_STYLE_FOCUS = 'style_focus'
/** Default metronome on when Slow/Play expose it. */
export const PREF_METRONOME_DEFAULT_ON = 'metronome_default_on'
/** `warm` | `concise` | `technical` — API prompt variant later. */
export const PREF_COACH_VOICE = 'coach_voice'
/** Last SoundFont profile that AlphaTab loaded successfully (`general_user` | `fluid_r3_mono`). */
export const PREF_LAST_SOUNDFONT_PROFILE = 'last_soundfont_profile'

/** Commit 62: skip `/session/tune` when `"1"`. */
export const PREF_SESSION_SKIP_TUNE = 'session_skip_tune'
/** Commit 62: active mic calibration profile id (`quiet-acoustic` | `electric-unplugged`). */
export const PREF_SESSION_MIC_PROFILE_ID = 'session_mic_profile_id'
/** Commit 62: JSON map of profile id → calibrated RMS gate threshold (after +6 dB headroom). */
export const PREF_SESSION_MIC_CALIBRATION_JSON = 'session_mic_calibration_json'

/** Commit 67: opaque id for server-side Spotify token bucket (never log). */
export const PREF_SPOTIFY_CLIENT_SESSION = 'spotify_client_session'
/** Commit 67: cached `SpotifyTasteProfile` JSON from last successful sync. */
export const PREF_SPOTIFY_TASTE_PROFILE_JSON = 'spotify_taste_profile_json'
/** Commit 68: cached derived `TasteProfile` JSON for curriculum/coach. */
export const PREF_TASTE_PROFILE_JSON = 'taste_profile_json'
/** Taste quiz experience tier; also shown in Settings and merged into API `learning_context`. */
export const PREF_EXPERIENCE_LEVEL = 'experience_level'

/** Commit 72: TTS voice coach — unset or non-`0` = enabled. */
export const PREF_VOICE_COACH_ENABLED = 'voice_coach_enabled'
/** Commit 72: speech rate 0.7–1.2 (stored as string float, default 1). */
export const PREF_VOICE_COACH_RATE = 'voice_coach_rate'
/** Commit 72: `default` | `female` | `male` — OS voice selection hint. */
export const PREF_VOICE_COACH_GENDER = 'voice_coach_gender'

export const COACH_VOICE_OPTIONS = ['warm', 'concise', 'technical'] as const
export type CoachVoiceId = (typeof COACH_VOICE_OPTIONS)[number]

/** Below this `transcription_confidence`, analysis is treated as “uncertain” for tab defaults. */
export const TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX = 0.72

/** v5: Library licks — full stem map JSON (guitar, bass, drums, …). */
export const MIGRATION_V5_LICKS_STEMS_JSON = 'ALTER TABLE licks ADD COLUMN stems_json TEXT'

/** v6: jam snapshots — canonical pitch/position maps + track/inference context. */
export const MIGRATION_V6_JAM_SNAPSHOT_CONTEXT = [
  'ALTER TABLE jam_snapshots ADD COLUMN pitch_class_weight_map TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN position_weight_map TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN inferred_scale_label TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN inference_confidence TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN track_id TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN track_label TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN track_key TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN track_bpm INTEGER',
] as const

/** v7: jam snapshots — reliability tags + confidence envelope fields. */
export const MIGRATION_V7_JAM_SNAPSHOT_RELIABILITY = [
  'ALTER TABLE jam_snapshots ADD COLUMN reliability_tags TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN reliability_confidence TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN reliability_signal_quality REAL',
] as const

/** v8: Library — persisted full analyzed lessons (not lick drill payloads). */
export const MIGRATION_V8_LESSONS = `
CREATE TABLE IF NOT EXISTS lessons (
  job_id TEXT PRIMARY KEY NOT NULL,
  lesson_json TEXT NOT NULL,
  song_title TEXT,
  artist TEXT,
  analyzed_at TEXT NOT NULL,
  section_count INTEGER NOT NULL DEFAULT 0
);
`

/** v9: rolling technique-session history for skill mutation weak-area detection (commit 63). */
export const MIGRATION_V9_SKILL_TECHNIQUE_ROLL =
  'ALTER TABLE skill_nodes ADD COLUMN technique_roll_json TEXT'

export const DEFAULT_SKILL_NODES: Array<{ id: string; label: string }> = [
  { id: 'pitch_accuracy', label: 'Pitch accuracy' },
  { id: 'phrasing', label: 'Phrasing' },
  { id: 'timing', label: 'Timing' },
  { id: 'bend_accuracy', label: 'Bend accuracy' },
  { id: 'vibrato_control', label: 'Vibrato control' },
]
