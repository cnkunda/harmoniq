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

export const COACH_VOICE_OPTIONS = ['warm', 'concise', 'technical'] as const
export type CoachVoiceId = (typeof COACH_VOICE_OPTIONS)[number]

/** Below this `transcription_confidence`, analysis is treated as “uncertain” for tab defaults. */
export const TRANSCRIPTION_CONFIDENCE_UNCERTAIN_MAX = 0.72

export const DEFAULT_SKILL_NODES: Array<{ id: string; label: string }> = [
  { id: 'pitch_accuracy', label: 'Pitch accuracy' },
  { id: 'phrasing', label: 'Phrasing' },
  { id: 'timing', label: 'Timing' },
  { id: 'bend_accuracy', label: 'Bend accuracy' },
  { id: 'vibrato_control', label: 'Vibrato control' },
]
