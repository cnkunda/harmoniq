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

/** Rollback for v4: remove added columns. */
export const ROLLBACK_V4_SESSIONS_REVIEW = [
  'ALTER TABLE sessions DROP COLUMN IF EXISTS review_snapshot',
  'ALTER TABLE sessions DROP COLUMN IF EXISTS waveform_user_path',
  'ALTER TABLE sessions DROP COLUMN IF EXISTS waveform_ref_path',
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
/** Commit 76: user can skip daily pre-session mood check. */
export const PREF_MOOD_CHECK_SKIP = 'mood_check_skip'
/** Commit 76: YYYY-MM-DD key for last day mood prompt was shown. */
export const PREF_MOOD_CHECK_LAST_SHOWN_DAY = 'mood_check_last_shown_day'
/** Commit 76: most recent chosen mood from pre-session check. */
export const PREF_MOOD_CHECK_LAST_MOOD = 'mood_check_last_mood'
/** Commit 92: musical tolerance mode for scoring (expressive | technique). */
export const PREF_MUSICAL_TOLERANCE_MODE = 'musical_tolerance_mode'
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

/** Commit 97: Preferred tab variant across sessions (`full` | `skeleton` | `alt`). */
export const PREF_TAB_VARIANT = 'tab_variant'
/** Commit 97: Whether lyrics strip is shown by default. */
export const PREF_SHOW_LYRICS = 'show_lyrics'
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

/** Rollback for v5: remove stems_json column. */
export const ROLLBACK_V5_LICKS_STEMS_JSON = 'ALTER TABLE licks DROP COLUMN IF EXISTS stems_json'

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

/** Rollback for v6: remove added columns. */
export const ROLLBACK_V6_JAM_SNAPSHOT_CONTEXT = [
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS pitch_class_weight_map',
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS position_weight_map',
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS inferred_scale_label',
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS inference_confidence',
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS track_id',
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS track_label',
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS track_key',
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS track_bpm',
] as const

/** v7: jam snapshots — reliability tags + confidence envelope fields. */
export const MIGRATION_V7_JAM_SNAPSHOT_RELIABILITY = [
  'ALTER TABLE jam_snapshots ADD COLUMN reliability_tags TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN reliability_confidence TEXT',
  'ALTER TABLE jam_snapshots ADD COLUMN reliability_signal_quality REAL',
] as const

/** Rollback for v7: remove added columns. */
export const ROLLBACK_V7_JAM_SNAPSHOT_RELIABILITY = [
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS reliability_tags',
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS reliability_confidence',
  'ALTER TABLE jam_snapshots DROP COLUMN IF EXISTS reliability_signal_quality',
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

/** Rollback for v8: drop lessons table. */
export const ROLLBACK_V8_LESSONS = 'DROP TABLE IF EXISTS lessons'

/** v9: rolling technique-session history for skill mutation weak-area detection (commit 63). */
export const MIGRATION_V9_SKILL_TECHNIQUE_ROLL =
  'ALTER TABLE skill_nodes ADD COLUMN technique_roll_json TEXT'

/** Rollback for v9: remove technique_roll_json column. */
export const ROLLBACK_V9_SKILL_TECHNIQUE_ROLL =
  'ALTER TABLE skill_nodes DROP COLUMN IF EXISTS technique_roll_json'

/** v10: practice plan completion rows (Jam “Complete session”). */
export const MIGRATION_V10_PRACTICE_PLAN_COMPLETIONS = `
CREATE TABLE IF NOT EXISTS practice_plan_completions (
  id TEXT PRIMARY KEY NOT NULL,
  completed_at TEXT NOT NULL,
  plan_json TEXT NOT NULL
);
`

/** Rollback for v10: drop practice_plan_completions table. */
export const ROLLBACK_V10_PRACTICE_PLAN_COMPLETIONS = 'DROP TABLE IF EXISTS practice_plan_completions'

/** Commit 75: ghost reference takes — section-scoped playback under live capture + Review overlay. */
export const MIGRATION_V11_SESSION_GHOST = [
  'ALTER TABLE sessions ADD COLUMN job_id TEXT',
  'ALTER TABLE sessions ADD COLUMN section_index INTEGER',
  'ALTER TABLE sessions ADD COLUMN is_ghost_reference INTEGER NOT NULL DEFAULT 0',
  'ALTER TABLE sessions ADD COLUMN ghost_anchor_sec REAL',
  'ALTER TABLE sessions ADD COLUMN ghost_audio_base64 TEXT',
] as const

/** Rollback for v11: remove added columns. */
export const ROLLBACK_V11_SESSION_GHOST = [
  'ALTER TABLE sessions DROP COLUMN IF EXISTS job_id',
  'ALTER TABLE sessions DROP COLUMN IF EXISTS section_index',
  'ALTER TABLE sessions DROP COLUMN IF EXISTS is_ghost_reference',
  'ALTER TABLE sessions DROP COLUMN IF EXISTS ghost_anchor_sec',
  'ALTER TABLE sessions DROP COLUMN IF EXISTS ghost_audio_base64',
] as const

/** Commit 75 — mime for inline/native ghost blobs (decoder hint). */
export const MIGRATION_V12_SESSION_GHOST_MIME = 'ALTER TABLE sessions ADD COLUMN ghost_recording_mime TEXT'

/** Rollback for v12: remove ghost_recording_mime column. */
export const ROLLBACK_V12_SESSION_GHOST_MIME = 'ALTER TABLE sessions DROP COLUMN IF EXISTS ghost_recording_mime'

/** Commit 76: mood captured at session save time for later progress analysis. */
export const MIGRATION_V13_SESSION_MOOD = 'ALTER TABLE sessions ADD COLUMN mood TEXT'

/** Rollback for v13: remove mood column. */
export const ROLLBACK_V13_SESSION_MOOD = 'ALTER TABLE sessions DROP COLUMN IF EXISTS mood'

/** v14: skill_nodes schema_version field for Jazz Extensions support (commit 88). */
export const MIGRATION_V14_SKILL_NODES_SCHEMA_VERSION = 'ALTER TABLE skill_nodes ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1'

/** Rollback for v14: remove schema_version column. */
export const ROLLBACK_V14_SKILL_NODES_SCHEMA_VERSION = 'ALTER TABLE skill_nodes DROP COLUMN IF EXISTS schema_version'

export const DEFAULT_SKILL_NODES: Array<{ id: string; label: string }> = [
  { id: 'pitch_accuracy', label: 'Pitch accuracy' },
  { id: 'phrasing', label: 'Phrasing' },
  { id: 'timing', label: 'Timing' },
  { id: 'bend_accuracy', label: 'Bend accuracy' },
  { id: 'vibrato_control', label: 'Vibrato control' },
]
