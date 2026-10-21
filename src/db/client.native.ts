import * as SQLite from 'expo-sqlite'

import { tryHomeSuggestionFromLesson } from '@/src/db/homeSuggestionFromLesson'
import { tryLibraryHomeSuggestion } from '@/src/db/homeSuggestionFromLicks'
import { logMigration, validateSessionsPreservation, validateSkillNodesPreservation } from '@/src/db/migrations'
import {
    DB_NAME,
    DEFAULT_SKILL_NODES,
    MIGRATION_TABLE_SQL,
    MIGRATION_V1,
    MIGRATION_V10_PRACTICE_PLAN_COMPLETIONS,
    MIGRATION_V11_SESSION_GHOST,
    MIGRATION_V12_SESSION_GHOST_MIME,
    MIGRATION_V13_SESSION_MOOD,
    MIGRATION_V14_SKILL_NODES_SCHEMA_VERSION,
    MIGRATION_V15_JAM_SNAPSHOT_SUMMARY,
    MIGRATION_V16_JAM_SNAPSHOT_INFERRED_MODE,
    MIGRATION_V17_USER_FEEDBACK,
    MIGRATION_V17_USER_FEEDBACK_UNIQUE_INDEX,
    MIGRATION_V18_JAM_SNAPSHOT_SUMMARY_STATUS,
    MIGRATION_V19_ANALYTICS_EVENTS,
    MIGRATION_V20_PRACTICE_PLANS,
    MIGRATION_V3_APP_PREFS,
    MIGRATION_V4_SESSIONS_REVIEW,
    MIGRATION_V5_LICKS_STEMS_JSON,
    MIGRATION_V6_JAM_SNAPSHOT_CONTEXT,
    MIGRATION_V7_JAM_SNAPSHOT_RELIABILITY,
    MIGRATION_V8_LESSONS,
    MIGRATION_V9_SKILL_TECHNIQUE_ROLL,
    PREF_EXPERIENCE_LEVEL,
    PREF_ONBOARDING_COMPLETE,
    PREF_TASTE_PROFILE_JSON,
    ROLLBACK_V10_PRACTICE_PLAN_COMPLETIONS,
    ROLLBACK_V11_SESSION_GHOST,
    ROLLBACK_V12_SESSION_GHOST_MIME,
    ROLLBACK_V13_SESSION_MOOD,
    ROLLBACK_V14_SKILL_NODES_SCHEMA_VERSION,
    ROLLBACK_V15_JAM_SNAPSHOT_SUMMARY,
    ROLLBACK_V16_JAM_SNAPSHOT_INFERRED_MODE,
    ROLLBACK_V17_USER_FEEDBACK,
    ROLLBACK_V18_JAM_SNAPSHOT_SUMMARY_STATUS,
    ROLLBACK_V19_ANALYTICS_EVENTS,
    ROLLBACK_V20_PRACTICE_PLANS,
    ROLLBACK_V4_SESSIONS_REVIEW,
    ROLLBACK_V5_LICKS_STEMS_JSON,
    ROLLBACK_V6_JAM_SNAPSHOT_CONTEXT,
    ROLLBACK_V7_JAM_SNAPSHOT_RELIABILITY,
    ROLLBACK_V8_LESSONS,
    ROLLBACK_V9_SKILL_TECHNIQUE_ROLL
} from '@/src/db/schema'
import type {
    AnalyticsEventRow,
    GhostReferenceRow,
    HomeSuggestion,
    JamSnapshotInsertInput,
    JamSnapshotRow,
    LatestSessionSongRow,
    LessonListRow,
    LickInsertInput,
    LickRow,
    NodeSessionSnippet,
    PracticePlanCompletionInsertInput,
    PracticePlanCompletionRow,
    PracticePlanRow,
    PracticePlanStartInput,
    PracticePlanStateUpdate,
    PracticePlanStatus,
    ReviewSkillUpdateInput,
    SessionArchiveRow,
    SessionInsertInput,
    SessionJournalRow,
    SkillNodeRow,
    SkillSessionMutationRow,
    UserFeedbackInsertInput,
    UserFeedbackRow,
    UserFeedbackStats,
} from '@/src/db/types'
import { formatJournalPlainText } from '@/src/settings/formatJournalExport'
import { buildFeedbackStats } from '@/src/utils/feedback'
import { deriveSkillNodeAfterSession } from '@/src/spaced/sm2'
import type { LessonJSON, TasteProfilePayload } from '@/src/types'

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

function parseInferenceConfidence(raw: string | null | undefined): 'low' | 'medium' | 'high' | null {
  if (raw === 'low' || raw === 'medium' || raw === 'high') return raw
  return null
}

function parseProgressConfidence(raw: string | null | undefined): 'low' | 'medium' | 'high' | null {
  if (raw === 'low' || raw === 'medium' || raw === 'high') return raw
  return null
}

async function applyMigrations(): Promise<void> {
  const db = await getDb()
  await db.execAsync(MIGRATION_TABLE_SQL)
  const row = await db.getFirstAsync<{ version: number }>('SELECT MAX(version) as version FROM schema_migrations')
  const current = row?.version ?? 0
  
  // Helper to apply migration with rollback support
  async function applyMigrationWithRollback(
    version: number,
    upSql: string | string[],
    downSql: string | readonly string[],
    validateBefore?: () => Promise<{ valid: boolean; error?: string }>,
  ): Promise<void> {
    try {
      // Validate before applying if validation function provided
      if (validateBefore) {
        const validation = await validateBefore()
        if (!validation.valid) {
          throw new Error(`Validation failed: ${validation.error}`)
        }
      }
      
      // Apply migration
      const statements = Array.isArray(upSql) ? upSql : [upSql]
      for (const stmt of statements) {
        await db.execAsync(stmt)
      }
      
      // Record migration
      await db.runAsync(
        'INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)',
        version,
        new Date().toISOString(),
      )
      
      logMigration({ version, success: true }, 'native')
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      console.error(`[db/native] Migration v${version} failed, attempting rollback: ${error}`)
      
      try {
        const rollbackStatements = Array.isArray(downSql) ? downSql : [downSql]
        for (const stmt of rollbackStatements) {
          await db.execAsync(stmt)
        }
        logMigration({ version, success: false, error, rolledBack: true }, 'native')
      } catch (rollbackError) {
        const rbError = rollbackError instanceof Error ? rollbackError.message : String(rollbackError)
        logMigration({ version, success: false, error: `${error}; Rollback failed: ${rbError}` }, 'native')
      }
      
      throw e
    }
  }
  
  if (current < 1) {
    await applyMigrationWithRollback(1, MIGRATION_V1, 'DROP TABLE IF EXISTS skill_nodes; DROP TABLE IF EXISTS sessions; DROP TABLE IF EXISTS licks; DROP TABLE IF EXISTS jam_snapshots')
  }
  if (current < 2) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(skill_nodes)')
    const hasRep = (cols ?? []).some((c) => c.name === 'sm2_repetitions')
    if (!hasRep) {
      await applyMigrationWithRollback(2, 'ALTER TABLE skill_nodes ADD COLUMN sm2_repetitions INTEGER NOT NULL DEFAULT 0', 'ALTER TABLE skill_nodes DROP COLUMN sm2_repetitions')
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 2, new Date().toISOString())
    }
  }
  if (current < 3) {
    await applyMigrationWithRollback(3, MIGRATION_V3_APP_PREFS, 'DROP TABLE IF EXISTS app_prefs')
  }
  if (current < 4) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(sessions)')
    const names = new Set((cols ?? []).map((c) => c.name))
    const pendingStatements: string[] = []
    for (const stmt of MIGRATION_V4_SESSIONS_REVIEW) {
      const col = stmt.includes('review_snapshot')
        ? 'review_snapshot'
        : stmt.includes('waveform_user_path')
          ? 'waveform_user_path'
          : 'waveform_ref_path'
      if (!names.has(col)) {
        pendingStatements.push(stmt)
        names.add(col)
      }
    }
    if (pendingStatements.length > 0) {
      await applyMigrationWithRollback(4, pendingStatements, ROLLBACK_V4_SESSIONS_REVIEW, async () => validateSessionsPreservation(getSessionCount))
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 4, new Date().toISOString())
    }
  }
  if (current < 5) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(licks)')
    const names = new Set((cols ?? []).map((c) => c.name))
    if (!names.has('stems_json')) {
      await applyMigrationWithRollback(5, MIGRATION_V5_LICKS_STEMS_JSON, ROLLBACK_V5_LICKS_STEMS_JSON)
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 5, new Date().toISOString())
    }
  }
  if (current < 6) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(jam_snapshots)')
    const names = new Set((cols ?? []).map((c) => c.name))
    const pendingStatements: string[] = []
    for (const stmt of MIGRATION_V6_JAM_SNAPSHOT_CONTEXT) {
      const col = stmt.split(' ADD COLUMN ')[1]?.split(' ')[0]
      if (!col) continue
      if (!names.has(col)) {
        pendingStatements.push(stmt)
        names.add(col)
      }
    }
    if (pendingStatements.length > 0) {
      await applyMigrationWithRollback(6, pendingStatements, ROLLBACK_V6_JAM_SNAPSHOT_CONTEXT)
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 6, new Date().toISOString())
    }
  }
  if (current < 7) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(jam_snapshots)')
    const names = new Set((cols ?? []).map((c) => c.name))
    const pendingStatements: string[] = []
    for (const stmt of MIGRATION_V7_JAM_SNAPSHOT_RELIABILITY) {
      const col = stmt.split(' ADD COLUMN ')[1]?.split(' ')[0]
      if (!col) continue
      if (!names.has(col)) {
        pendingStatements.push(stmt)
        names.add(col)
      }
    }
    if (pendingStatements.length > 0) {
      await applyMigrationWithRollback(7, pendingStatements, ROLLBACK_V7_JAM_SNAPSHOT_RELIABILITY)
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 7, new Date().toISOString())
    }
  }
  if (current < 8) {
    await applyMigrationWithRollback(8, MIGRATION_V8_LESSONS, ROLLBACK_V8_LESSONS)
  }
  if (current < 9) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(skill_nodes)')
    const names = new Set((cols ?? []).map((c) => c.name))
    if (!names.has('technique_roll_json')) {
      await applyMigrationWithRollback(9, MIGRATION_V9_SKILL_TECHNIQUE_ROLL, ROLLBACK_V9_SKILL_TECHNIQUE_ROLL, async () => validateSkillNodesPreservation(getAllSkillNodes))
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 9, new Date().toISOString())
    }
  }
  if (current < 10) {
    await applyMigrationWithRollback(10, MIGRATION_V10_PRACTICE_PLAN_COMPLETIONS, ROLLBACK_V10_PRACTICE_PLAN_COMPLETIONS)
  }
  if (current < 11) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(sessions)')
    const names = new Set((cols ?? []).map((c) => c.name))
    const pendingStatements: string[] = []
    for (const stmt of MIGRATION_V11_SESSION_GHOST) {
      const col = stmt.split(' ADD COLUMN ')[1]?.split(' ')[0]
      if (!col) continue
      if (!names.has(col)) {
        pendingStatements.push(stmt)
        names.add(col)
      }
    }
    if (pendingStatements.length > 0) {
      await applyMigrationWithRollback(11, pendingStatements, ROLLBACK_V11_SESSION_GHOST, async () => validateSessionsPreservation(getSessionCount))
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 11, new Date().toISOString())
    }
  }
  if (current < 12) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(sessions)')
    const names = new Set((cols ?? []).map((c) => c.name))
    if (!names.has('ghost_recording_mime')) {
      await applyMigrationWithRollback(12, MIGRATION_V12_SESSION_GHOST_MIME, ROLLBACK_V12_SESSION_GHOST_MIME)
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 12, new Date().toISOString())
    }
  }
  if (current < 13) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(sessions)')
    const names = new Set((cols ?? []).map((c) => c.name))
    if (!names.has('mood')) {
      await applyMigrationWithRollback(13, MIGRATION_V13_SESSION_MOOD, ROLLBACK_V13_SESSION_MOOD)
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 13, new Date().toISOString())
    }
  }
  if (current < 14) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(skill_nodes)')
    const names = new Set((cols ?? []).map((c) => c.name))
    if (!names.has('schema_version')) {
      await applyMigrationWithRollback(14, MIGRATION_V14_SKILL_NODES_SCHEMA_VERSION, ROLLBACK_V14_SKILL_NODES_SCHEMA_VERSION, async () => validateSkillNodesPreservation(getAllSkillNodes))
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 14, new Date().toISOString())
    }
  }
  if (current < 15) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(jam_snapshots)')
    const names = new Set((cols ?? []).map((c) => c.name))
    const pendingStatements: string[] = []
    for (const stmt of MIGRATION_V15_JAM_SNAPSHOT_SUMMARY) {
      const col = stmt.split(' ADD COLUMN ')[1]?.split(' ')[0]
      if (!col) continue
      if (!names.has(col)) {
        pendingStatements.push(stmt)
        names.add(col)
      }
    }
    if (pendingStatements.length > 0) {
      await applyMigrationWithRollback(15, pendingStatements, ROLLBACK_V15_JAM_SNAPSHOT_SUMMARY)
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 15, new Date().toISOString())
    }
  }
  if (current < 16) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(jam_snapshots)')
    const names = new Set((cols ?? []).map((c) => c.name))
    if (!names.has('inferred_mode')) {
      await applyMigrationWithRollback(16, MIGRATION_V16_JAM_SNAPSHOT_INFERRED_MODE, ROLLBACK_V16_JAM_SNAPSHOT_INFERRED_MODE)
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 16, new Date().toISOString())
    }
  }
  if (current < 17) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(user_feedback)')
    if ((cols ?? []).length === 0) {
      await applyMigrationWithRollback(17, MIGRATION_V17_USER_FEEDBACK, ROLLBACK_V17_USER_FEEDBACK)
    } else {
      const indexes = await db.getAllAsync<{ name: string; unique: number }>('PRAGMA index_list(user_feedback)')
      const hasUnique = (indexes ?? []).some(
        (index) => index.name === 'idx_user_feedback_job_type_event' || index.unique === 1,
      )
      if (!hasUnique) {
        await applyMigrationWithRollback(
          17,
          MIGRATION_V17_USER_FEEDBACK_UNIQUE_INDEX,
          'DROP INDEX IF EXISTS idx_user_feedback_job_type_event',
        )
      } else {
        await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 17, new Date().toISOString())
      }
    }
  }
  if (current < 18) {
    const cols = await db.getAllAsync<{ name: string }>('PRAGMA table_info(jam_snapshots)')
    const names = new Set((cols ?? []).map((c) => c.name))
    if (!names.has('summary_status')) {
      await applyMigrationWithRollback(
        18,
        MIGRATION_V18_JAM_SNAPSHOT_SUMMARY_STATUS,
        ROLLBACK_V18_JAM_SNAPSHOT_SUMMARY_STATUS,
      )
    } else {
      await db.runAsync('INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)', 18, new Date().toISOString())
    }
  }
  if (current < 19) {
    await applyMigrationWithRollback(19, MIGRATION_V19_ANALYTICS_EVENTS, ROLLBACK_V19_ANALYTICS_EVENTS)
  }
  if (current < 20) {
    await applyMigrationWithRollback(20, MIGRATION_V20_PRACTICE_PLANS, ROLLBACK_V20_PRACTICE_PLANS)
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
      review_snapshot, waveform_user_path, waveform_ref_path,
      job_id, section_index, is_ghost_reference, ghost_anchor_sec, ghost_audio_base64, ghost_recording_mime, mood)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
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
    input.job_id ?? null,
    input.section_index ?? null,
    input.is_ghost_reference === true ? 1 : 0,
    input.ghost_anchor_sec ?? null,
    input.ghost_audio_base64 ?? null,
    input.ghost_recording_mime ?? null,
    input.mood ?? null,
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
  job_id: string | null
  section_index: number | null
  is_ghost_reference: number | null
  ghost_anchor_sec: number | null
  ghost_audio_base64: string | null
  ghost_recording_mime: string | null
  mood: 'focused' | 'loose' | 'tired' | 'on_fire' | null
}

function mapSessionJournalRow(r: SessionRowDb): SessionJournalRow {
  const snap = r.review_snapshot
  const ghostRef =
    typeof r.is_ghost_reference === 'number' ? r.is_ghost_reference !== 0 : Boolean(r.is_ghost_reference)
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
    job_id: r.job_id ?? null,
    section_index: typeof r.section_index === 'number' ? r.section_index : null,
    is_ghost_reference: ghostRef,
    ghost_anchor_sec:
      typeof r.ghost_anchor_sec === 'number' && Number.isFinite(r.ghost_anchor_sec) ? r.ghost_anchor_sec : null,
    ghost_audio_base64: r.ghost_audio_base64 ?? null,
    ghost_recording_mime: r.ghost_recording_mime ?? null,
    mood: r.mood ?? null,
  }
}

export async function listSessionsJournal(): Promise<SessionJournalRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<SessionRowDb>(
    `SELECT id, song_title, artist, section_label, date, coach_review, pitch_accuracy, phrasing_score, nodes_targeted,
            review_snapshot, waveform_user_path, waveform_ref_path,
            job_id, section_index, is_ghost_reference, ghost_anchor_sec, ghost_audio_base64, ghost_recording_mime, mood
     FROM sessions ORDER BY date DESC`,
  )
  return (rows ?? []).map(mapSessionJournalRow)
}

export async function listSessionsArchive(): Promise<SessionArchiveRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<SessionRowDb>(
    `SELECT id, song_title, artist, section_label, date, coach_review, pitch_accuracy, phrasing_score, nodes_targeted,
            review_snapshot, waveform_user_path, waveform_ref_path,
            job_id, section_index, is_ghost_reference, ghost_anchor_sec, ghost_audio_base64, ghost_recording_mime, mood
     FROM sessions ORDER BY date DESC`,
  )
  return (rows ?? []).map((r) => ({
    ...mapSessionJournalRow(r),
    review_snapshot: r.review_snapshot ?? null,
  }))
}

export async function getSessionById(id: string): Promise<SessionArchiveRow | null> {
  await initDb()
  const db = await getDb()
  const r = await db.getFirstAsync<SessionRowDb>(
    `SELECT id, song_title, artist, section_label, date, coach_review, pitch_accuracy, phrasing_score, nodes_targeted,
            review_snapshot, waveform_user_path, waveform_ref_path,
            job_id, section_index, is_ghost_reference, ghost_anchor_sec, ghost_audio_base64, ghost_recording_mime, mood
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

/** Commit 69: taste quiz completion — `TasteProfile` prefs + experience-mapped skill scores. */
export async function commitTasteQuizProfile(
  taste: TasteProfilePayload,
  experienceLevel: 'beginner' | 'intermediate' | 'advanced',
): Promise<void> {
  await initDb()
  const db = await getDb()
  const tier = experienceLevel === 'beginner' ? 0.2 : experienceLevel === 'advanced' ? 0.7 : 0.5
  await setAppPref(PREF_TASTE_PROFILE_JSON, JSON.stringify(taste))
  await setAppPref(PREF_EXPERIENCE_LEVEL, experienceLevel)
  const rows = await getAllSkillNodes()
  for (const n of DEFAULT_SKILL_NODES) {
    const row = rows.find((r) => r.id === n.id)
    if (!row) continue
    const u = deriveSkillNodeAfterSession(
      {
        score: row.score,
        easiness_factor: row.easiness_factor,
        interval_days: row.interval_days,
        sm2_repetitions: row.sm2_repetitions,
        sessions_count: row.sessions_count,
      },
      tier,
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
    const licks = await getLicks()
    const lib = tryLibraryHomeSuggestion(licks)
    if (lib) return lib
    const { useLessonStore } = await import('@/src/stores/lessonStore')
    const active = tryHomeSuggestionFromLesson(useLessonStore.getState().lesson)
    if (active) return active
    return { kind: 'cold_start' }
  }
  const db = await getDb()
  const node = await db.getFirstAsync<SkillNodeRow>(
    `SELECT * FROM skill_nodes
     ORDER BY (next_review_date IS NULL) DESC, next_review_date ASC, id ASC
     LIMIT 1`,
  )
  if (!node) {
    const licks = await getLicks()
    const lib = tryLibraryHomeSuggestion(licks)
    if (lib) return lib
    const { useLessonStore } = await import('@/src/stores/lessonStore')
    const active = tryHomeSuggestionFromLesson(useLessonStore.getState().lesson)
    if (active) return active
    return { kind: 'cold_start' }
  }
  return { kind: 'ready', node, song }
}

export async function applySessionMutation(updates: SkillSessionMutationRow[]): Promise<void> {
  if (updates.length === 0) return
  await initDb()
  const db = await getDb()
  for (const u of updates) {
    await db.runAsync(
      'UPDATE skill_nodes SET score = ?, technique_roll_json = ? WHERE id = ?',
      u.score,
      u.technique_roll_json,
      u.id,
    )
  }
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
    const confidence = input.node_confidence_map?.[id]
    const reliability = input.node_reliability_map?.[id]
    const u = deriveSkillNodeAfterSession(
      {
        score: row.score ?? 0,
        easiness_factor: row.easiness_factor ?? 2.5,
        interval_days: row.interval_days ?? 1,
        sm2_repetitions: row.sm2_repetitions ?? 0,
        sessions_count: row.sessions_count ?? 0,
      },
      sessionScore,
      {
        accuracyScore01: input.session_accuracy01 ?? sessionScore,
        timingStability01: input.session_timing_stability01 ?? sessionScore,
        reliabilityScore01: typeof reliability === 'number' ? reliability : undefined,
        confidence: confidence === 'low' || confidence === 'medium' || confidence === 'high' ? confidence : undefined,
        reliabilityFlags: input.reliability_flags ?? [],
      },
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
  const pitchMap = input.pitch_class_weight_map ?? input.scale_position_map ?? {}
  const positionMap = input.position_weight_map ?? {}
  await db.runAsync(
    `INSERT OR REPLACE INTO jam_snapshots
     (id, date, duration_seconds, scale_position_map, pitch_class_weight_map, position_weight_map,
      inferred_scale_label, inferred_mode, inference_confidence, track_id, track_label, track_key, track_bpm,
      reliability_tags, reliability_confidence, reliability_signal_quality,
      recurring_gestures, coach_summary, summary_bundle_json, phrases_json, summary_status)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    input.id,
    input.date,
    input.duration_seconds,
    JSON.stringify(pitchMap),
    JSON.stringify(pitchMap),
    JSON.stringify(positionMap),
    input.inferred_scale_label ?? null,
    input.inferred_mode ?? null,
    input.inference_confidence ?? null,
    input.track_id ?? null,
    input.track_label ?? null,
    input.track_key ?? null,
    input.track_bpm ?? null,
    JSON.stringify(input.reliability_tags ?? []),
    input.reliability_confidence ?? null,
    input.reliability_signal_quality ?? null,
    JSON.stringify(input.recurring_gestures ?? []),
    input.coach_summary,
    input.summary_bundle_json ?? null,
    input.phrases_json ?? null,
    input.summary_status ?? null,
  )
}

export async function updateJamSnapshotSummary(
  id: string,
  input: {
    summary_bundle_json: string | null
    coach_summary: string
    summary_status: 'pending' | 'ready' | 'failed' | 'skipped'
  },
): Promise<void> {
  await initDb()
  const db = await getDb()
  const result = await db.runAsync(
    `UPDATE jam_snapshots
     SET summary_bundle_json = ?, coach_summary = ?, summary_status = ?
     WHERE id = ?`,
    input.summary_bundle_json,
    input.coach_summary,
    input.summary_status,
    id,
  )
  if (result.changes === 0) {
    throw new Error(`Jam snapshot ${id} not found`)
  }
}

export async function listJamSnapshots(): Promise<JamSnapshotRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<{
    id: string
    date: string
    duration_seconds: number
    scale_position_map: string | null
    pitch_class_weight_map: string | null
    position_weight_map: string | null
    inferred_scale_label: string | null
    inferred_mode: string | null
    inference_confidence: string | null
    track_id: string | null
    track_label: string | null
    track_key: string | null
    track_bpm: number | null
    reliability_tags: string | null
    reliability_confidence: string | null
    reliability_signal_quality: number | null
    recurring_gestures: string | null
    coach_summary: string | null
    summary_bundle_json: string | null
    phrases_json: string | null
    summary_status: string | null
  }>('SELECT * FROM jam_snapshots ORDER BY date DESC')
  return (rows ?? []).map((r) => ({
    id: r.id,
    date: r.date,
    duration_seconds: r.duration_seconds,
    scale_position_map: parseJsonNumberRecord(r.pitch_class_weight_map ?? r.scale_position_map),
    pitch_class_weight_map: parseJsonNumberRecord(r.pitch_class_weight_map ?? r.scale_position_map),
    position_weight_map: parseJsonNumberRecord(r.position_weight_map),
    inferred_scale_label: r.inferred_scale_label ?? null,
    inferred_mode: r.inferred_mode ?? null,
    inference_confidence: parseInferenceConfidence(r.inference_confidence),
    track_id: r.track_id ?? null,
    track_label: r.track_label ?? null,
    track_key: r.track_key ?? null,
    track_bpm: typeof r.track_bpm === 'number' ? r.track_bpm : null,
    reliability_tags: parseJsonArray<string>(r.reliability_tags),
    reliability_confidence: parseProgressConfidence(r.reliability_confidence),
    reliability_signal_quality:
      typeof r.reliability_signal_quality === 'number' && Number.isFinite(r.reliability_signal_quality)
        ? r.reliability_signal_quality
        : null,
    recurring_gestures: parseJsonArray<string>(r.recurring_gestures),
    coach_summary: r.coach_summary ?? '',
    summary_bundle_json: r.summary_bundle_json ?? null,
    phrases_json: r.phrases_json ?? null,
    summary_status:
      r.summary_status === 'pending' ||
      r.summary_status === 'ready' ||
      r.summary_status === 'failed' ||
      r.summary_status === 'skipped'
        ? r.summary_status
        : null,
  }))
}

export async function insertPracticePlanCompletionRow(input: PracticePlanCompletionInsertInput): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.runAsync(
    `INSERT OR REPLACE INTO practice_plan_completions (id, completed_at, plan_json) VALUES (?, ?, ?)`,
    input.id,
    input.completed_at,
    input.plan_json,
  )
}

export async function listPracticePlanCompletions(): Promise<PracticePlanCompletionRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<{ id: string; completed_at: string; plan_json: string }>(
    'SELECT id, completed_at, plan_json FROM practice_plan_completions ORDER BY completed_at DESC',
  )
  return (rows ?? []).map((r) => ({
    id: r.id,
    completed_at: r.completed_at,
    plan_json: r.plan_json,
  }))
}

function mapPracticePlanRow(row: PracticePlanRow): PracticePlanRow {
  return {
    plan_id: row.plan_id,
    status:
      row.status === 'active' || row.status === 'completed' || row.status === 'abandoned'
        ? row.status
        : 'active',
    current_slot_index: Number.isFinite(row.current_slot_index) ? Math.max(0, Math.floor(row.current_slot_index)) : 0,
    plan_json: row.plan_json,
    slot_results_json: row.slot_results_json || '[]',
    adaptation_log: row.adaptation_log || '[]',
    started_at: row.started_at,
    updated_at: row.updated_at,
  }
}

export async function startActivePracticePlanRow(input: PracticePlanStartInput): Promise<void> {
  await initDb()
  const db = await getDb()
  const now = new Date().toISOString()
  const startedAt = input.started_at ?? now
  await db.runAsync(
    `UPDATE practice_plans SET status = 'abandoned', updated_at = ? WHERE status = 'active'`,
    now,
  )
  await db.runAsync(
    `INSERT OR REPLACE INTO practice_plans
     (plan_id, status, current_slot_index, plan_json, slot_results_json, adaptation_log, started_at, updated_at)
     VALUES (?, 'active', ?, ?, ?, ?, ?, ?)`,
    input.plan_id,
    Math.max(0, Math.floor(input.current_slot_index ?? 0)),
    input.plan_json,
    input.slot_results_json ?? '[]',
    input.adaptation_log ?? '[]',
    startedAt,
    now,
  )
}

export async function getActivePracticePlanRow(): Promise<PracticePlanRow | null> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<PracticePlanRow>(
    `SELECT plan_id, status, current_slot_index, plan_json, slot_results_json, adaptation_log, started_at, updated_at
     FROM practice_plans WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1`,
  )
  const row = rows?.[0]
  return row ? mapPracticePlanRow(row) : null
}

export async function updatePracticePlanRowState(
  planId: string,
  update: PracticePlanStateUpdate,
): Promise<void> {
  await initDb()
  const db = await getDb()
  const fields: string[] = []
  const args: (string | number)[] = []
  if (update.plan_json !== undefined) {
    fields.push('plan_json = ?')
    args.push(update.plan_json)
  }
  if (update.current_slot_index !== undefined) {
    fields.push('current_slot_index = ?')
    args.push(Math.max(0, Math.floor(update.current_slot_index)))
  }
  if (update.slot_results_json !== undefined) {
    fields.push('slot_results_json = ?')
    args.push(update.slot_results_json)
  }
  if (update.adaptation_log !== undefined) {
    fields.push('adaptation_log = ?')
    args.push(update.adaptation_log)
  }
  fields.push('updated_at = ?')
  args.push(update.updated_at ?? new Date().toISOString())
  args.push(planId)
  await db.runAsync(
    `UPDATE practice_plans SET ${fields.join(', ')} WHERE plan_id = ?`,
    ...args,
  )
}

export async function markPracticePlanStatus(
  planId: string,
  status: PracticePlanStatus,
): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.runAsync(
    'UPDATE practice_plans SET status = ?, updated_at = ? WHERE plan_id = ?',
    status,
    new Date().toISOString(),
    planId,
  )
}

export async function clearPracticePlans(): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.execAsync('DELETE FROM practice_plans')
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
  await db.execAsync('DELETE FROM lessons')
  await db.execAsync('DELETE FROM jam_snapshots')
  await db.execAsync('DELETE FROM practice_plan_completions')
  await db.execAsync('DELETE FROM practice_plans')
  await db.execAsync('DELETE FROM user_feedback')
  await db.execAsync('DELETE FROM analytics_events')
  await db.execAsync(
    `UPDATE skill_nodes SET score = 0, sessions_count = 0, last_session_date = NULL,
     easiness_factor = 2.5, interval_days = 1, next_review_date = NULL, sm2_repetitions = 0,
     technique_roll_json = NULL`,
  )
}

export async function insertLickRow(input: LickInsertInput): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.runAsync(
    `INSERT OR REPLACE INTO licks
     (id, song_title, artist, key, scale, position, tab_gp5_base64, audio_segment_path, stems_json, coach_oneliner, technique_tags, user_annotations, date_saved)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    input.id,
    input.song_title,
    input.artist,
    input.key,
    input.scale,
    input.position,
    input.tab_gp5_base64,
    input.audio_segment_path,
    input.stems_json,
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
    stems_json: string | null
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
    stems_json: r.stems_json ?? null,
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
    stems_json: string | null
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
    stems_json: r.stems_json ?? null,
    coach_oneliner: r.coach_oneliner,
    technique_tags: parseJsonArray<string>(r.technique_tags),
    user_annotations: parseJsonArray<{ bar: number; text: string }>(r.user_annotations),
    date_saved: r.date_saved,
  }))
}

export async function upsertLessonFromAnalysis(lesson: LessonJSON): Promise<void> {
  const id = typeof lesson.job_id === 'string' ? lesson.job_id.trim() : ''
  if (!id || id.startsWith('lick-')) return
  await initDb()
  const db = await getDb()
  const sectionCount = Array.isArray(lesson.sections) ? lesson.sections.length : 0
  const analyzedAt = new Date().toISOString()
  await db.runAsync(
    `INSERT INTO lessons (job_id, lesson_json, song_title, artist, analyzed_at, section_count)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(job_id) DO UPDATE SET
       lesson_json = excluded.lesson_json,
       song_title = excluded.song_title,
       artist = excluded.artist,
       section_count = excluded.section_count`,
    id,
    JSON.stringify(lesson),
    typeof lesson.song_title === 'string' ? lesson.song_title : null,
    typeof lesson.artist === 'string' ? lesson.artist : null,
    analyzedAt,
    sectionCount,
  )
}

export async function listLessonsJournal(): Promise<LessonListRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<{
    job_id: string
    song_title: string | null
    artist: string | null
    analyzed_at: string
    section_count: number
  }>('SELECT job_id, song_title, artist, analyzed_at, section_count FROM lessons ORDER BY analyzed_at DESC')
  return (rows ?? []).map((r) => ({
    job_id: r.job_id,
    song_title: r.song_title,
    artist: r.artist,
    analyzed_at: r.analyzed_at,
    section_count: typeof r.section_count === 'number' && Number.isFinite(r.section_count) ? r.section_count : 0,
  }))
}

export async function getLessonByJobId(jobId: string): Promise<LessonJSON | null> {
  await initDb()
  const db = await getDb()
  const r = await db.getFirstAsync<{ lesson_json: string }>('SELECT lesson_json FROM lessons WHERE job_id = ?', jobId)
  if (!r?.lesson_json) return null
  try {
    return JSON.parse(r.lesson_json) as LessonJSON
  } catch {
    return null
  }
}

export async function deleteLessonByJobId(jobId: string): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.runAsync('DELETE FROM lessons WHERE job_id = ?', jobId)
}

/** Commit 75: Most recent ghost reference take for this lesson section (for Play mix + Review overlay). */
export async function getLatestGhostReference(jobId: string, sectionIndex: number): Promise<GhostReferenceRow | null> {
  await initDb()
  const db = await getDb()
  const jid = jobId.trim()
  if (!jid) return null
  try {
    const row = await db.getFirstAsync<{
      id: string
      date: string
      waveform_user_path: string | null
      ghost_anchor_sec: number | null
      ghost_audio_base64: string | null
      ghost_recording_mime: string | null
    }>(
      `SELECT id, date, waveform_user_path, ghost_anchor_sec, ghost_audio_base64, ghost_recording_mime
       FROM sessions
       WHERE job_id = ? AND section_index = ? AND is_ghost_reference = 1
       ORDER BY date DESC LIMIT 1`,
      jid,
      sectionIndex,
    )
    if (!row) return null
    return {
      id: row.id,
      date: row.date,
      waveform_user_path: row.waveform_user_path ?? null,
      ghost_anchor_sec:
        typeof row.ghost_anchor_sec === 'number' && Number.isFinite(row.ghost_anchor_sec)
          ? row.ghost_anchor_sec
          : null,
      ghost_audio_base64: row.ghost_audio_base64 ?? null,
      ghost_recording_mime: row.ghost_recording_mime ?? null,
    }
  } catch (e) {
    if (__DEV__) console.warn('[db] getLatestGhostReference failed', jid, sectionIndex, e)
    return null
  }
}

/** No-op on native (lesson cache is web IDB only). */
export async function hydrateWebLessonStore(): Promise<void> {}

function newFeedbackId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

const USER_FEEDBACK_COLUMNS =
  'id, job_id, song_id, user_id, timestamp, feedback_type, event_index, original_value, corrected_value, reason'

/** Commit 159: upsert by (job_id, feedback_type, event_index). */
export async function upsertUserFeedback(input: UserFeedbackInsertInput): Promise<UserFeedbackRow> {
  await initDb()
  const db = await getDb()
  const row: UserFeedbackRow = {
    id: input.id ?? newFeedbackId(),
    job_id: input.job_id,
    song_id: input.song_id,
    user_id: input.user_id,
    timestamp: input.timestamp ?? new Date().toISOString(),
    feedback_type: input.feedback_type,
    event_index: input.event_index,
    original_value: input.original_value,
    corrected_value: input.corrected_value,
    reason: input.reason,
  }
  await db.runAsync(
    `INSERT INTO user_feedback (${USER_FEEDBACK_COLUMNS})
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(job_id, feedback_type, event_index) DO UPDATE SET
       id = excluded.id,
       song_id = excluded.song_id,
       user_id = excluded.user_id,
       timestamp = excluded.timestamp,
       original_value = excluded.original_value,
       corrected_value = excluded.corrected_value,
       reason = excluded.reason`,
    row.id,
    row.job_id,
    row.song_id,
    row.user_id,
    row.timestamp,
    row.feedback_type,
    row.event_index,
    row.original_value,
    row.corrected_value,
    row.reason,
  )
  return row
}

export async function listUserFeedback(): Promise<UserFeedbackRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<UserFeedbackRow>(
    `SELECT ${USER_FEEDBACK_COLUMNS} FROM user_feedback ORDER BY timestamp DESC`,
  )
  return rows ?? []
}

export async function listUserFeedbackForJob(jobId: string): Promise<UserFeedbackRow[]> {
  await initDb()
  const db = await getDb()
  const jid = jobId.trim()
  if (!jid) return []
  const rows = await db.getAllAsync<UserFeedbackRow>(
    `SELECT ${USER_FEEDBACK_COLUMNS} FROM user_feedback WHERE job_id = ? ORDER BY timestamp DESC`,
    jid,
  )
  return rows ?? []
}

export async function deleteUserFeedback(id: string): Promise<void> {
  await initDb()
  const db = await getDb()
  await db.runAsync('DELETE FROM user_feedback WHERE id = ?', id)
}

export async function getUserFeedbackStats(): Promise<UserFeedbackStats> {
  return buildFeedbackStats(await listUserFeedback())
}

/** Commit 161: persist queued analytics events in one transaction. */
export async function insertAnalyticsEvents(rows: AnalyticsEventRow[]): Promise<void> {
  if (rows.length === 0) return
  await initDb()
  const db = await getDb()
  await db.withTransactionAsync(async () => {
    for (const row of rows) {
      await db.runAsync(
        `INSERT OR REPLACE INTO analytics_events (id, user_id, event_type, payload_json, timestamp)
         VALUES (?, ?, ?, ?, ?)`,
        row.id,
        row.user_id,
        row.event_type,
        row.payload_json,
        row.timestamp,
      )
    }
  })
}

/** Commit 161: newest-first analytics rows for metrics + export. */
export async function listAnalyticsEvents(): Promise<AnalyticsEventRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<AnalyticsEventRow>(
    `SELECT id, user_id, event_type, payload_json, timestamp
     FROM analytics_events ORDER BY timestamp DESC, id DESC`,
  )
  return rows ?? []
}
