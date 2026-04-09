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

export const DEFAULT_SKILL_NODES: Array<{ id: string; label: string }> = [
  { id: 'pitch_accuracy', label: 'Pitch accuracy' },
  { id: 'phrasing', label: 'Phrasing' },
  { id: 'timing', label: 'Timing' },
  { id: 'bend_accuracy', label: 'Bend accuracy' },
  { id: 'vibrato_control', label: 'Vibrato control' },
]
