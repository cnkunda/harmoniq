import * as SQLite from 'expo-sqlite'

import { DB_NAME, DEFAULT_SKILL_NODES, MIGRATION_TABLE_SQL, MIGRATION_V1 } from '@/src/db/schema'
import type { ReviewSkillUpdateInput, SessionInsertInput, SkillNodeRow } from '@/src/db/types'
import { deriveSkillNodeAfterSession } from '@/src/spaced/sm2'

type DbHandle = Awaited<ReturnType<typeof SQLite.openDatabaseAsync>>

let dbPromise: Promise<DbHandle> | null = null
let migrationPromise: Promise<void> | null = null

async function getDb(): Promise<DbHandle> {
  if (!dbPromise) dbPromise = SQLite.openDatabaseAsync(DB_NAME)
  return dbPromise
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
     (id, song_title, artist, section_label, date, coach_review, pitch_accuracy, phrasing_score, nodes_targeted)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    input.id,
    input.song_title,
    input.artist,
    input.section_label,
    input.date,
    input.coach_review,
    input.pitch_accuracy,
    input.phrasing_score,
    JSON.stringify(input.nodes_targeted ?? []),
  )
}

export async function getSessionCount(): Promise<number> {
  await initDb()
  const db = await getDb()
  const row = await db.getFirstAsync<{ c: number }>('SELECT COUNT(*) as c FROM sessions')
  return row?.c ?? 0
}

export async function getAllSkillNodes(): Promise<SkillNodeRow[]> {
  await initDb()
  const db = await getDb()
  const rows = await db.getAllAsync<SkillNodeRow>('SELECT * FROM skill_nodes ORDER BY id ASC')
  return rows ?? []
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
