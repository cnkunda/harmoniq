import * as SQLite from 'expo-sqlite'

import {
    DB_NAME,
    DEFAULT_SKILL_NODES,
    MIGRATION_TABLE_SQL,
    MIGRATION_V1,
    MIGRATION_V3_APP_PREFS,
    MIGRATION_V4_SESSIONS_REVIEW,
    PREF_ONBOARDING_COMPLETE,
} from '@/src/db/schema'
import { tryLibraryHomeSuggestion } from '@/src/db/homeSuggestionFromLicks'
import type {
  HomeSuggestion,
    JamSnapshotInsertInput,
    JamSnapshotRow,
    LatestSessionSongRow,
    LickInsertInput,
    LickRow,
    NodeSessionSnippet,
    ReviewSkillUpdateInput,
    SessionArchiveRow,
    SessionInsertInput,
    SessionJournalRow,
    SkillNodeRow,
} from '@/src/db/types'
import { formatJournalPlainText } from '@/src/settings/formatJournalExport'
import { deriveSkillNodeAfterSession } from '@/src/spaced/sm2'

type DbHandle = Awaited<ReturnType<typeof SQLite.openDatabaseAsync>>

let dbPromise: Promise<DbHandle> | null = null
let migrationPromise: Promise<void> | null = null

async function getDb(): Promise<DbHandle> {
  if (!dbPromise) dbPromise = SQLite.openDatabaseAsync(DB_NAME)
  return dbPromise
}

function parseJsonArray<T>(raw: string | null | undefined): T[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : []
  } catch {
    return []
  }
}

function parseJsonNumberRecord(raw: string | null | undefined): Record<string, number> {
  if (!raw) return {}
  try {
    const o = JSON.parse(raw) as unknown
    if (!o || typeof o !== 'object' || Array.isArray(o)) return {}
    const out: Record<string, number> = {}
    for (const [k, v] of Object.entries(o as Record<string, unknown>)) {
      if (typeof v === 'number' && Number.isFinite(v)) out[k] = v
    }
    return out
  } catch {
    return {}
  }
}

async function applyMigrations(): Promise<void> {
  const db = await getDb()
  await db.execAsync(MIGRATION_TABLE_SQL)
  const row = await db.getFirstAsync<{ version: number }>('SELECT MAX(version) as version FROM schema_migrations')
  const current = row?.version ?? 0
  if (current < 1) {
    await db.execAsync(MIGRATION_V1)
    await db.runAsync(
      'INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)',
      1,
      new Date().toISOString(),
    )
  }
  if (current < 2) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(skill_nodes)')
    const hasRep = (cols ?? []).some((c) => c.name === 'sm2_repetitions')
    if (!hasRep) {
      await db.execAsync('ALTER TABLE skill_nodes ADD COLUMN sm2_repetitions INTEGER NOT NULL DEFAULT 0')
    }
    await db.runAsync(
      'INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)',
      2,
      new Date().toISOString(),
    )
  }
  if (current < 3) {
    await db.execAsync(MIGRATION_V3_APP_PREFS)
    await db.runAsync(
      'INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)',
      3,
      new Date().toISOString(),
    )
  }
  if (current < 4) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(sessions)')
    const names = new Set((cols ?? []).map((c) => c.name))
    for (const stmt of MIGRATION_V4_SESSIONS_REVIEW) {
      const col = stmt.includes('review_snapshot')
        ? 'review_snapshot'
        : stmt.includes('waveform_user_path')
          ? 'waveform_user_path'
          : 'waveform_ref_path'
      if (!names.has(col)) {
        await db.execAsync(stmt)
        names.add(col)
      }
    }
    await db.runAsync(
      'INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)',
      4,
      new Date().toISOString(),
    )
  }
  for (const n of DEFAULT_SKILL_NODES) {
    await db.runAsync(
      `INSERT OR IGNORE INTO skill_nodes
      (id, label, score, sessions_count, last_session_date, easiness_factor, interval_days, next_review_date, sm2_repetitions)
      VALUES (?, ?, 0.0, 0, NULL, 2.5, 1, NULL, 0)`,
      n.id,
      n.label,
    )
  }
}

export async function initDb(): Promise<void> {
  if (!migrationPromise) migrationPromise = applyMigrations()
  await migrationPromise
}

export async function insertSessionRow(input: SessionInsertInput): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.runAsync(
    `INSERT OR REPLACE INTO sessions
     (id, song_title, artist, section_label, date, coach_review, pitch_accuracy, phrasing_score, nodes_targeted,
      review_snapshot, waveform_user_path, waveform_ref_path)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    input.id,
    input.song_title,
    input.artist,
    input.section_label,
    input.date,
    input.coach_review,
    input.pitch_accuracy,
    input.phrasing_score,
    JSON.stringify(input.nodes_targeted ?? []),
    input.review_snapshot ?? null,
    input.waveform_user_path ?? null,
    input.waveform_ref_path ?? null,
  )
}

export async function getSessionCount(): Promise<number> {
  await initDb()
  const db = await getDb()
  const row = await db.getFirstAsync<{ c: number }>('SELECT COUNT(*) as c FROM sessions')
  return row?.c ?? 0
}

type SessionRowDb = {
  id: string
  song_title: string | null
  artist: string | null
  section_label: string | null
  date: string
  coach_review: string | null
  pitch_accuracy: number | null
  phrasing_score: number | null
  nodes_targeted: string | null
  review_snapshot: string | null
  waveform_user_path: string | null
  waveform_ref_path: string | null
}

function mapSessionJournalRow(r: SessionRowDb): SessionJournalRow {
  const snap = r.review_snapshot
  return {
    id: r.id,
    song_title: r.song_title,
    artist: r.artist,
    section_label: r.section_label,
    date: r.date,
    coach_review: r.coach_review,
    pitch_accuracy: r.pitch_accuracy,
    phrasing_score: r.phrasing_score,
    nodes_targeted: parseJsonArray<string>(r.nodes_targeted),
    has_review_snapshot: snap != null && snap.trim() !== '',
    waveform_user_path: r.waveform_user_path ?? null,
    waveform_ref_path: r.waveform_ref_path ?? null,
  }
}

export async function listSessionsJournal(): Promise<SessionJournalRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<SessionRowDb>(
    `SELECT id, song_title, artist, section_label, date, coach_review, pitch_accuracy, phrasing_score, nodes_targeted,
            review_snapshot, waveform_user_path, waveform_ref_path
     FROM sessions ORDER BY date DESC`,
  )
  return (rows ?? []).map(mapSessionJournalRow)
}

export async function getSessionById(id: string): Promise<SessionArchiveRow | null> {
  await initDb()
  const db = await getDb()
  const r = await db.getFirstAsync<SessionRowDb>(
    `SELECT id, song_title, artist, section_label, date, coach_review, pitch_accuracy, phrasing_score, nodes_targeted,
            review_snapshot, waveform_user_path, waveform_ref_path
     FROM sessions WHERE id = ?`,
    id,
  )
  if (!r) return null
  const base = mapSessionJournalRow(r)
  return { ...base, review_snapshot: r.review_snapshot ?? null }
}

export async function getLatestSessionSnippetForNode(nodeId: string): Promise<NodeSessionSnippet | null> {
  await initDb()
  const db = await getDb()
  try {
    const row = await db.getFirstAsync<{
      coach_review: string | null
      date: string
      pitch_accuracy: number | null
      phrasing_score: number | null
    }>(
      `SELECT s.coach_review, s.date, s.pitch_accuracy, s.phrasing_score
       FROM sessions s, json_each(s.nodes_targeted) AS j
       WHERE j.value = ?
       ORDER BY s.date DESC LIMIT 1`,
      nodeId,
    )
    return row ?? null
  } catch (e) {
    if (__DEV__) console.warn('[db] getLatestSessionSnippetForNode failed', nodeId, e)
    return null
  }
}

export async function getAllSkillNodes(): Promise<SkillNodeRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<SkillNodeRow>('SELECT * FROM skill_nodes ORDER BY id ASC')
  return rows ?? []
}

export async function getAppPref(key: string): Promise<string | null> {
  await initDb()
  const db = await getDb()
  const row = await db.getFirstAsync<{ value: string }>('SELECT value FROM app_prefs WHERE key = ?', key)
  return row?.value ?? null
}

export async function setAppPref(key: string, value: string): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.runAsync('INSERT OR REPLACE INTO app_prefs (key, value) VALUES (?, ?)', key, value)
}

export async function getOnboardingComplete(): Promise<boolean> {
  const v = await getAppPref(PREF_ONBOARDING_COMPLETE)
  return v === '1'
}

export async function setOnboardingComplete(): Promise<void> {
  await setAppPref(PREF_ONBOARDING_COMPLETE, '1')
}

let placementCommitChain = Promise.resolve()

/** Idempotent: seeds nodes + sets onboarding flag once (serializes concurrent callers). */
export async function commitPlacementOnboarding(aggregatedNodeScores: Record<string, number>): Promise<void> {
  placementCommitChain = placementCommitChain.then(async () => {
    if (await getOnboardingComplete()) return
    await seedPlacementBaseline(aggregatedNodeScores)
    await setOnboardingComplete()
  })
  await placementCommitChain
}

/**
 * Placement baseline: one synthetic "session" per skill node from aggregated scores (PRIORITIES §32).
 * Ensures each default node has non-zero score + SM-2 fields.
 */
async function seedPlacementBaseline(aggregatedNodeScores: Record<string, number>): Promise<void> {
  await initDb()
  const db = await getDb()
  for (const n of DEFAULT_SKILL_NODES) {
    const raw = aggregatedNodeScores[n.id]
    const sessionScore =
      typeof raw === 'number' && Number.isFinite(raw) ? Math.max(0.05, Math.min(1, raw)) : 0.15
    const u = deriveSkillNodeAfterSession(
      {
        score: 0,
        easiness_factor: 2.5,
        interval_days: 1,
        sm2_repetitions: 0,
        sessions_count: 0,
      },
      sessionScore,
    )
    await db.runAsync(
      `UPDATE skill_nodes SET score = ?, easiness_factor = ?, interval_days = ?, sm2_repetitions = ?,
       next_review_date = ?, sessions_count = ?, last_session_date = ? WHERE id = ?`,
      u.score,
      u.easiness_factor,
      u.interval_days,
      u.sm2_repetitions,
      u.next_review_date,
      u.sessions_count,
      u.last_session_date,
      n.id,
    )
  }
}

export async function getLatestSessionWithSong(): Promise<LatestSessionSongRow | null> {
  await initDb()
  const db = await getDb()
  const row = await db.getFirstAsync<{
    song_title: string
    artist: string | null
    section_label: string | null
    date: string
  }>(
    `SELECT song_title, artist, section_label, date FROM sessions
     WHERE song_title IS NOT NULL AND LENGTH(TRIM(song_title)) > 0
     ORDER BY date DESC LIMIT 1`,
  )
  return row ?? null
}

export async function getHomeSuggestion(): Promise<HomeSuggestion> {
  await initDb()
  const song = await getLatestSessionWithSong()
  if (!song) {
    const lib = tryLibraryHomeSuggestion(await getLicks())
    return lib ?? { kind: 'cold_start' }
  }
  const db = await getDb()
  const node = await db.getFirstAsync<SkillNodeRow>(
    `SELECT * FROM skill_nodes
     ORDER BY (next_review_date IS NULL) DESC, next_review_date ASC, id ASC
     LIMIT 1`,
  )
  if (!node) {
    const lib = tryLibraryHomeSuggestion(await getLicks())
    return lib ?? { kind: 'cold_start' }
  }
  return { kind: 'ready', node, song }
}

export async function applyReviewSkillUpdates(input: ReviewSkillUpdateInput): Promise<void> {
  await initDb()
  const db = await getDb()
  for (const id of input.targeted_node_ids) {
    const row = await db.getFirstAsync<{
      id: string
      score: number | null
      sessions_count: number | null
      last_session_date: string | null
      easiness_factor: number | null
      interval_days: number | null
      next_review_date: string | null
      sm2_repetitions: number | null
    }>('SELECT * FROM skill_nodes WHERE id = ?', id)
    if (!row) continue
    const sessionScore = input.node_scores[id]
    if (typeof sessionScore !== 'number' || !Number.isFinite(sessionScore)) continue
    const u = deriveSkillNodeAfterSession(
      {
        score: row.score ?? 0,
        easiness_factor: row.easiness_factor ?? 2.5,
        interval_days: row.interval_days ?? 1,
        sm2_repetitions: row.sm2_repetitions ?? 0,
        sessions_count: row.sessions_count ?? 0,
      },
      sessionScore,
    )
    await db.runAsync(
      `UPDATE skill_nodes SET score = ?, easiness_factor = ?, interval_days = ?, sm2_repetitions = ?,
       next_review_date = ?, sessions_count = ?, last_session_date = ? WHERE id = ?`,
      u.score,
      u.easiness_factor,
      u.interval_days,
      u.sm2_repetitions,
      u.next_review_date,
      u.sessions_count,
      u.last_session_date,
      id,
    )
  }
}

export async function insertJamSnapshotRow(input: JamSnapshotInsertInput): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.runAsync(
    `INSERT OR REPLACE INTO jam_snapshots
     (id, date, duration_seconds, scale_position_map, recurring_gestures, coach_summary)
     VALUES (?, ?, ?, ?, ?, ?)`,
    input.id,
    input.date,
    input.duration_seconds,
    JSON.stringify(input.scale_position_map ?? {}),
    JSON.stringify(input.recurring_gestures ?? []),
    input.coach_summary,
  )
}

export async function listJamSnapshots(): Promise<JamSnapshotRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<{
    id: string
    date: string
    duration_seconds: number
    scale_position_map: string | null
    recurring_gestures: string | null
    coach_summary: string | null
  }>('SELECT * FROM jam_snapshots ORDER BY date DESC')
  return (rows ?? []).map((r) => ({
    id: r.id,
    date: r.date,
    duration_seconds: r.duration_seconds,
    scale_position_map: parseJsonNumberRecord(r.scale_position_map),
    recurring_gestures: parseJsonArray<string>(r.recurring_gestures),
    coach_summary: r.coach_summary ?? '',
  }))
}

export async function buildJournalExportText(): Promise<string> {
  const [sessions, licks, jams, skills] = await Promise.all([
    listSessionsJournal(),
    getLicks(),
    listJamSnapshots(),
    getAllSkillNodes(),
  ])
  return formatJournalPlainText({
    exportedAt: new Date().toISOString(),
    sessions,
    licks,
    jams,
    skills,
  })
}

export async function clearAllPracticeData(): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.execAsync('DELETE FROM sessions')
  await db.execAsync('DELETE FROM licks')
  await db.execAsync('DELETE FROM jam_snapshots')
  await db.execAsync(
    `UPDATE skill_nodes SET score = 0, sessions_count = 0, last_session_date = NULL,
     easiness_factor = 2.5, interval_days = 1, next_review_date = NULL, sm2_repetitions = 0`,
  )
}

export async function insertLickRow(input: LickInsertInput): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.runAsync(
    `INSERT OR REPLACE INTO licks
     (id, song_title, artist, key, scale, position, tab_gp5_base64, audio_segment_path, coach_oneliner, technique_tags, user_annotations, date_saved)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    input.id,
    input.song_title,
    input.artist,
    input.key,
    input.scale,
    input.position,
    input.tab_gp5_base64,
    input.audio_segment_path,
    input.coach_oneliner,
    JSON.stringify(input.technique_tags ?? []),
    JSON.stringify(input.user_annotations ?? []),
    input.date_saved,
  )
}

export async function deleteLickById(id: string): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.runAsync('DELETE FROM licks WHERE id = ?', id)
}

export async function getLickById(id: string): Promise<LickRow | null> {
  await initDb()
  const db = await getDb()
  const r = await db.getFirstAsync<{
    id: string
    song_title: string | null
    artist: string | null
    key: string | null
    scale: string | null
    position: string | null
    tab_gp5_base64: string
    audio_segment_path: string | null
    coach_oneliner: string | null
    technique_tags: string | null
    user_annotations: string | null
    date_saved: string
  }>('SELECT * FROM licks WHERE id = ?', id)
  if (!r) return null
  return {
    id: r.id,
    song_title: r.song_title,
    artist: r.artist,
    key: r.key,
    scale: r.scale,
    position: r.position,
    tab_gp5_base64: r.tab_gp5_base64,
    audio_segment_path: r.audio_segment_path,
    coach_oneliner: r.coach_oneliner,
    technique_tags: parseJsonArray<string>(r.technique_tags),
    user_annotations: parseJsonArray<{ bar: number; text: string }>(r.user_annotations),
    date_saved: r.date_saved,
  }
}

export async function getLicks(): Promise<LickRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<{
    id: string
    song_title: string | null
    artist: string | null
    key: string | null
    scale: string | null
    position: string | null
    tab_gp5_base64: string
    audio_segment_path: string | null
    coach_oneliner: string | null
    technique_tags: string | null
    user_annotations: string | null
    date_saved: string
  }>('SELECT * FROM licks ORDER BY date_saved DESC')
  return (rows ?? []).map((r) => ({
    id: r.id,
    song_title: r.song_title,
    artist: r.artist,
    key: r.key,
    scale: r.scale,
    position: r.position,
    tab_gp5_base64: r.tab_gp5_base64,
    audio_segment_path: r.audio_segment_path,
    coach_oneliner: r.coach_oneliner,
    technique_tags: parseJsonArray<string>(r.technique_tags),
    user_annotations: parseJsonArray<{ bar: number; text: string }>(r.user_annotations),
    date_saved: r.date_saved,
  }))
}

/** No-op on native (lesson cache is web IDB only). */
export async function hydrateWebLessonStore(): Promise<void> {}
