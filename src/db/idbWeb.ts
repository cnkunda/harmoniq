/**
 * IndexedDB persistence for web (PRIORITIES §38).
 * Best-effort: if `indexedDB` is missing, callers no-op persistence and stay in-memory only.
 *
 * Limits: single-tab demo scale; large `review_snapshot` rows can approach per-origin quota (~50MB+).
 */

import type { LessonJSON } from '@/src/types'

import type { JamSnapshotInsertInput, LessonPersistRow, LickRow, SessionArchiveRow, SkillNodeRow } from '@/src/db/types'

const DB_NAME = 'harmoniq_web_v1'
const DB_VERSION = 2

const S_PREFS = 'app_prefs'
const S_SESSIONS = 'sessions'
const S_SKILL_NODES = 'skill_nodes'
const S_LICKS = 'licks'
const S_JAM = 'jam_snapshots'
const S_LESSON = 'lesson_cache'
const S_LESSONS = 'lessons'

type PrefRow = { key: string; value: string }
type LessonCacheRow = { id: 'latest'; lesson: LessonJSON; savedAt: string }

function idbAvailable(): boolean {
  return typeof indexedDB !== 'undefined'
}

export async function openHarmoniqIdb(): Promise<IDBDatabase | null> {
  if (!idbAvailable()) return null
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB_NAME, DB_VERSION)
    r.onerror = () => reject(r.error ?? new Error('IndexedDB open failed'))
    r.onsuccess = () => resolve(r.result)
    r.onupgradeneeded = () => {
      const db = r.result
      if (!db.objectStoreNames.contains(S_PREFS)) {
        db.createObjectStore(S_PREFS, { keyPath: 'key' })
      }
      if (!db.objectStoreNames.contains(S_SESSIONS)) {
        db.createObjectStore(S_SESSIONS, { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains(S_SKILL_NODES)) {
        db.createObjectStore(S_SKILL_NODES, { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains(S_LICKS)) {
        db.createObjectStore(S_LICKS, { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains(S_JAM)) {
        db.createObjectStore(S_JAM, { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains(S_LESSON)) {
        db.createObjectStore(S_LESSON, { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains(S_LESSONS)) {
        db.createObjectStore(S_LESSONS, { keyPath: 'job_id' })
      }
    }
  })
}

async function getAllStore<T>(db: IDBDatabase, name: string): Promise<T[]> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(name, 'readonly')
    tx.onerror = () => reject(tx.error ?? new Error('read tx failed'))
    const store = tx.objectStore(name)
    const req = store.getAll()
    req.onerror = () => reject(req.error ?? new Error('getAll failed'))
    req.onsuccess = () => resolve((req.result as T[]) ?? [])
  })
}

async function clearStore(db: IDBDatabase, name: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(name, 'readwrite')
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB transaction failed'))
    tx.oncomplete = () => resolve()
    tx.objectStore(name).clear()
  })
}

async function putAll<T extends { id: string }>(db: IDBDatabase, name: string, rows: T[]): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(name, 'readwrite')
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB transaction failed'))
    tx.oncomplete = () => resolve()
    const store = tx.objectStore(name)
    const cr = store.clear()
    cr.onerror = () => reject(cr.error ?? new Error('clear failed'))
    cr.onsuccess = () => {
      for (const row of rows) {
        const clone = JSON.parse(JSON.stringify(row)) as T
        store.put(clone)
      }
    }
  })
}

async function putAllPrefs(db: IDBDatabase, prefs: Map<string, string>): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(S_PREFS, 'readwrite')
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB transaction failed'))
    tx.oncomplete = () => resolve()
    const store = tx.objectStore(S_PREFS)
    const cr = store.clear()
    cr.onerror = () => reject(cr.error ?? new Error('clear prefs failed'))
    cr.onsuccess = () => {
      for (const [key, value] of prefs) {
        store.put({ key, value })
      }
    }
  })
}

export type IdbHydration = {
  prefs: PrefRow[]
  sessions: SessionArchiveRow[]
  skillNodes: SkillNodeRow[]
  licks: LickRow[]
  jams: JamSnapshotInsertInput[]
  lesson: LessonJSON | null
  lessons: LessonPersistRow[]
}

export async function idbLoadEverything(db: IDBDatabase): Promise<IdbHydration> {
  const [prefs, sessions, skillNodes, licks, jams, lessonRows, lessonCatalog] = await Promise.all([
    getAllStore<PrefRow>(db, S_PREFS),
    getAllStore<SessionArchiveRow>(db, S_SESSIONS),
    getAllStore<SkillNodeRow>(db, S_SKILL_NODES),
    getAllStore<LickRow>(db, S_LICKS),
    getAllStore<JamSnapshotInsertInput>(db, S_JAM),
    getAllStore<LessonCacheRow>(db, S_LESSON),
    db.objectStoreNames.contains(S_LESSONS) ? getAllStore<LessonPersistRow>(db, S_LESSONS) : Promise.resolve([]),
  ])
  const latest = lessonRows.find((r) => r.id === 'latest')
  return {
    prefs,
    sessions,
    skillNodes,
    licks,
    jams,
    lesson: latest?.lesson ?? null,
    lessons: lessonCatalog,
  }
}

export async function idbPersistSessions(db: IDBDatabase | null, sessions: SessionArchiveRow[]): Promise<void> {
  if (!db) return
  await putAll(db, S_SESSIONS, sessions)
}

export async function idbPersistPrefs(db: IDBDatabase | null, prefs: Map<string, string>): Promise<void> {
  if (!db) return
  await putAllPrefs(db, prefs)
}

export async function idbPersistSkillNodes(db: IDBDatabase | null, nodes: SkillNodeRow[]): Promise<void> {
  if (!db) return
  await putAll(db, S_SKILL_NODES, nodes)
}

export async function idbPersistLicks(db: IDBDatabase | null, rows: LickRow[]): Promise<void> {
  if (!db) return
  await putAll(db, S_LICKS, rows)
}

export async function idbPersistJams(db: IDBDatabase | null, rows: JamSnapshotInsertInput[]): Promise<void> {
  if (!db) return
  await putAll(db, S_JAM, rows)
}

export async function idbPersistLessons(db: IDBDatabase | null, rows: LessonPersistRow[]): Promise<void> {
  if (!db || !db.objectStoreNames.contains(S_LESSONS)) return
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(S_LESSONS, 'readwrite')
    tx.onerror = () => reject(tx.error ?? new Error('IndexedDB transaction failed'))
    tx.oncomplete = () => resolve()
    const store = tx.objectStore(S_LESSONS)
    const cr = store.clear()
    cr.onerror = () => reject(cr.error ?? new Error('clear lessons failed'))
    cr.onsuccess = () => {
      for (const row of rows) {
        store.put(JSON.parse(JSON.stringify(row)) as LessonPersistRow)
      }
    }
  })
}

export async function idbWriteLessonCache(db: IDBDatabase | null, lesson: LessonJSON): Promise<void> {
  if (!db) return
  const row: LessonCacheRow = { id: 'latest', lesson, savedAt: new Date().toISOString() }
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(S_LESSON, 'readwrite')
    tx.onerror = () => reject(tx.error ?? new Error('lesson cache write failed'))
    tx.oncomplete = () => resolve()
    tx.objectStore(S_LESSON).put(row)
  })
}

export async function idbReadLessonCache(db: IDBDatabase | null): Promise<LessonJSON | null> {
  if (!db) return null
  return new Promise((resolve, reject) => {
    const tx = db.transaction(S_LESSON, 'readonly')
    tx.onerror = () => reject(tx.error ?? new Error('lesson cache read failed'))
    const req = tx.objectStore(S_LESSON).get('latest')
    req.onerror = () => reject(req.error ?? new Error('get lesson failed'))
    req.onsuccess = () => {
      const row = req.result as LessonCacheRow | undefined
      resolve(row?.lesson ?? null)
    }
  })
}

export async function idbClearLessonCache(db: IDBDatabase | null): Promise<void> {
  if (!db) return
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(S_LESSON, 'readwrite')
    tx.onerror = () => reject(tx.error ?? new Error('lesson cache clear failed'))
    tx.oncomplete = () => resolve()
    tx.objectStore(S_LESSON).delete('latest')
  })
}

/** Clears practice tables in IDB; keeps `app_prefs` only. Also clears lesson cache and lesson catalog. */
export async function idbClearPracticeStores(db: IDBDatabase | null): Promise<void> {
  if (!db) return
  await clearStore(db, S_SESSIONS)
  await clearStore(db, S_LICKS)
  await clearStore(db, S_JAM)
  await clearStore(db, S_SKILL_NODES)
  if (db.objectStoreNames.contains(S_LESSONS)) {
    await clearStore(db, S_LESSONS)
  }
  await clearStore(db, S_LESSON)
}

let harmoniqIdbHandle: IDBDatabase | null = null

export function setHarmoniqIdbHandle(db: IDBDatabase | null): void {
  harmoniqIdbHandle = db
}

export function getHarmoniqIdbHandle(): IDBDatabase | null {
  return harmoniqIdbHandle
}
