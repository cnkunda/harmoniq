import {
    getHarmoniqIdbHandle,
    idbClearPracticeStores,
    idbLoadEverything,
    idbPersistJams,
    idbPersistLicks,
    idbPersistPrefs,
    idbPersistSessions,
    idbPersistSkillNodes,
    idbReadLessonCache,
    openHarmoniqIdb,
    setHarmoniqIdbHandle,
    type IdbHydration,
} from '@/src/db/idbWeb'
import { DEFAULT_SKILL_NODES, PREF_ONBOARDING_COMPLETE } from '@/src/db/schema'
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

const skillNodes = new Map<string, SkillNodeRow>()
/** Newest-first (matches native `ORDER BY date DESC`). */
const sessionLog: SessionArchiveRow[] = []
const sessionSongLog: LatestSessionSongRow[] = []
const appPrefs = new Map<string, string>()
const licks: LickRow[] = []
const jamSnapshots: JamSnapshotInsertInput[] = []

let initPromise: Promise<void> | null = null

function defaultSkillRow(def: { id: string; label: string }): SkillNodeRow {
  return {
    id: def.id,
    label: def.label,
    score: 0,
    sessions_count: 0,
    last_session_date: null,
    easiness_factor: 2.5,
    interval_days: 1,
    next_review_date: null,
    sm2_repetitions: 0,
  }
}

function seedWebSkillNodes(): void {
  if (skillNodes.size > 0) return
  for (const n of DEFAULT_SKILL_NODES) {
    skillNodes.set(n.id, defaultSkillRow(n))
  }
}

function mergeSkillNodesWithDefaults(): void {
  for (const n of DEFAULT_SKILL_NODES) {
    if (!skillNodes.has(n.id)) skillNodes.set(n.id, defaultSkillRow(n))
  }
}

function rebuildSessionSongLogFromSessions(): void {
  sessionSongLog.length = 0
  const chronological = [...sessionLog].sort((a, b) => a.date.localeCompare(b.date))
  for (const s of chronological) {
    if (s.song_title?.trim()) {
      sessionSongLog.push({
        song_title: s.song_title.trim(),
        artist: s.artist,
        section_label: s.section_label,
        date: s.date,
      })
    }
  }
}

function applySkillNodesFromIdb(rows: SkillNodeRow[]): void {
  skillNodes.clear()
  const byId = new Map(rows.map((r) => [r.id, r]))
  for (const n of DEFAULT_SKILL_NODES) {
    skillNodes.set(n.id, byId.get(n.id) ?? defaultSkillRow(n))
  }
}

function applyHydration(h: IdbHydration): void {
  appPrefs.clear()
  for (const p of h.prefs) {
    appPrefs.set(p.key, p.value)
  }
  sessionLog.length = 0
  const sessionsSorted = [...h.sessions].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
  sessionLog.push(...sessionsSorted)
  rebuildSessionSongLogFromSessions()
  if (h.skillNodes.length > 0) {
    applySkillNodesFromIdb(h.skillNodes)
  } else {
    skillNodes.clear()
  }
  licks.length = 0
  licks.push(...h.licks)
  jamSnapshots.length = 0
  const jamsSorted = [...h.jams].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
  jamSnapshots.push(...jamsSorted)
}

async function flushPrefs(): Promise<void> {
  await idbPersistPrefs(getHarmoniqIdbHandle(), appPrefs)
}

async function flushSessions(): Promise<void> {
  await idbPersistSessions(getHarmoniqIdbHandle(), sessionLog)
}

async function flushSkillNodes(): Promise<void> {
  await idbPersistSkillNodes(getHarmoniqIdbHandle(), Array.from(skillNodes.values()))
}

async function flushLicks(): Promise<void> {
  await idbPersistLicks(getHarmoniqIdbHandle(), licks)
}

async function flushJams(): Promise<void> {
  await idbPersistJams(getHarmoniqIdbHandle(), jamSnapshots)
}

/**
 * Web: IndexedDB mirrors practice tables + prefs; lesson JSON cached separately (PRIORITIES §38).
 */
export async function initDb(): Promise<void> {
  if (!initPromise) {
    initPromise = (async () => {
      try {
        const db = await openHarmoniqIdb()
        setHarmoniqIdbHandle(db)
        if (db) {
          const h = await idbLoadEverything(db)
          applyHydration(h)
        }
      } catch (e) {
        if (__DEV__) console.warn('[db/web] IndexedDB init failed — using memory only', e)
        setHarmoniqIdbHandle(null)
      }
      seedWebSkillNodes()
      mergeSkillNodesWithDefaults()
    })()
  }
  await initPromise
}

function sessionRowFromInput(input: SessionInsertInput): SessionArchiveRow {
  const snap = input.review_snapshot ?? null
  return {
    id: input.id,
    song_title: input.song_title,
    artist: input.artist,
    section_label: input.section_label,
    date: input.date,
    coach_review: input.coach_review,
    pitch_accuracy: input.pitch_accuracy,
    phrasing_score: input.phrasing_score,
    nodes_targeted: input.nodes_targeted ?? [],
    has_review_snapshot: snap != null && snap.trim() !== '',
    waveform_user_path: input.waveform_user_path ?? null,
    waveform_ref_path: input.waveform_ref_path ?? null,
    review_snapshot: snap,
  }
}

export async function insertSessionRow(input: SessionInsertInput): Promise<void> {
  const row = sessionRowFromInput(input)
  const i = sessionLog.findIndex((x) => x.id === row.id)
  if (i >= 0) sessionLog[i] = row
  else sessionLog.unshift(row)
  if (input.song_title?.trim()) {
    sessionSongLog.push({
      song_title: input.song_title.trim(),
      artist: input.artist,
      section_label: input.section_label,
      date: input.date,
    })
  }
  await flushSessions()
}

export async function getSessionCount(): Promise<number> {
  return sessionLog.length
}

export async function listSessionsJournal(): Promise<SessionJournalRow[]> {
  seedWebSkillNodes()
  return [...sessionLog]
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
    .map((r) => ({
      id: r.id,
      song_title: r.song_title,
      artist: r.artist,
      section_label: r.section_label,
      date: r.date,
      coach_review: r.coach_review,
      pitch_accuracy: r.pitch_accuracy,
      phrasing_score: r.phrasing_score,
      nodes_targeted: r.nodes_targeted,
      has_review_snapshot: r.has_review_snapshot,
      waveform_user_path: r.waveform_user_path,
      waveform_ref_path: r.waveform_ref_path,
    }))
}

export async function getSessionById(id: string): Promise<SessionArchiveRow | null> {
  seedWebSkillNodes()
  return sessionLog.find((x) => x.id === id) ?? null
}

export async function getLatestSessionSnippetForNode(nodeId: string): Promise<NodeSessionSnippet | null> {
  seedWebSkillNodes()
  for (const s of sessionLog) {
    if (s.nodes_targeted.includes(nodeId)) {
      return {
        coach_review: s.coach_review,
        date: s.date,
        pitch_accuracy: s.pitch_accuracy,
        phrasing_score: s.phrasing_score,
      }
    }
  }
  return null
}

export async function getAllSkillNodes(): Promise<SkillNodeRow[]> {
  seedWebSkillNodes()
  return Array.from(skillNodes.values()).sort((a, b) => a.id.localeCompare(b.id))
}

function pickEarliestDueSkillNode(nodes: SkillNodeRow[]): SkillNodeRow | null {
  if (nodes.length === 0) return null
  return [...nodes].sort((a, b) => {
    const ad = a.next_review_date
    const bd = b.next_review_date
    if (ad == null && bd == null) return a.id.localeCompare(b.id)
    if (ad == null) return -1
    if (bd == null) return 1
    if (ad === bd) return a.id.localeCompare(b.id)
    return ad < bd ? -1 : 1
  })[0]
}

export async function getAppPref(key: string): Promise<string | null> {
  seedWebSkillNodes()
  return appPrefs.get(key) ?? null
}

export async function setAppPref(key: string, value: string): Promise<void> {
  seedWebSkillNodes()
  appPrefs.set(key, value)
  await flushPrefs()
}

export async function getOnboardingComplete(): Promise<boolean> {
  const v = await getAppPref(PREF_ONBOARDING_COMPLETE)
  return v === '1'
}

export async function setOnboardingComplete(): Promise<void> {
  await setAppPref(PREF_ONBOARDING_COMPLETE, '1')
}

async function seedPlacementBaseline(aggregatedNodeScores: Record<string, number>): Promise<void> {
  seedWebSkillNodes()
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
    const row = skillNodes.get(n.id)
    if (!row) continue
    skillNodes.set(n.id, {
      ...row,
      score: u.score,
      easiness_factor: u.easiness_factor,
      interval_days: u.interval_days,
      sm2_repetitions: u.sm2_repetitions,
      next_review_date: u.next_review_date,
      sessions_count: u.sessions_count,
      last_session_date: u.last_session_date,
    })
  }
}

let placementCommitChain = Promise.resolve()

export async function commitPlacementOnboarding(aggregatedNodeScores: Record<string, number>): Promise<void> {
  placementCommitChain = placementCommitChain.then(async () => {
    if (await getOnboardingComplete()) return
    await seedPlacementBaseline(aggregatedNodeScores)
    await setOnboardingComplete()
    await flushSkillNodes()
  })
  await placementCommitChain
}

export async function getLatestSessionWithSong(): Promise<LatestSessionSongRow | null> {
  seedWebSkillNodes()
  for (let i = sessionSongLog.length - 1; i >= 0; i--) {
    const s = sessionSongLog[i]
    if (s.song_title.trim()) return s
  }
  return null
}

export async function getHomeSuggestion(): Promise<HomeSuggestion> {
  seedWebSkillNodes()
  const song = await getLatestSessionWithSong()
  if (!song) {
    const lib = tryLibraryHomeSuggestion(await getLicks())
    return lib ?? { kind: 'cold_start' }
  }
  const nodes = await getAllSkillNodes()
  const node = pickEarliestDueSkillNode(nodes)
  if (!node) {
    const lib = tryLibraryHomeSuggestion(await getLicks())
    return lib ?? { kind: 'cold_start' }
  }
  return { kind: 'ready', node, song }
}

export async function applyReviewSkillUpdates(input: ReviewSkillUpdateInput): Promise<void> {
  seedWebSkillNodes()
  for (const id of input.targeted_node_ids) {
    const row = skillNodes.get(id)
    if (!row) continue
    const sessionScore = input.node_scores[id]
    if (typeof sessionScore !== 'number' || !Number.isFinite(sessionScore)) continue
    const u = deriveSkillNodeAfterSession(
      {
        score: row.score,
        easiness_factor: row.easiness_factor,
        interval_days: row.interval_days,
        sm2_repetitions: row.sm2_repetitions,
        sessions_count: row.sessions_count,
      },
      sessionScore,
    )
    skillNodes.set(id, {
      ...row,
      score: u.score,
      easiness_factor: u.easiness_factor,
      interval_days: u.interval_days,
      sm2_repetitions: u.sm2_repetitions,
      next_review_date: u.next_review_date,
      sessions_count: u.sessions_count,
      last_session_date: u.last_session_date,
    })
  }
  await flushSkillNodes()
}

export async function insertJamSnapshotRow(input: JamSnapshotInsertInput): Promise<void> {
  seedWebSkillNodes()
  jamSnapshots.unshift({ ...input })
  await flushJams()
}

export async function listJamSnapshots(): Promise<JamSnapshotRow[]> {
  seedWebSkillNodes()
  return [...jamSnapshots]
    .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0))
    .map((j) => ({
      id: j.id,
      date: j.date,
      duration_seconds: j.duration_seconds,
      scale_position_map: { ...j.scale_position_map },
      recurring_gestures: [...j.recurring_gestures],
      coach_summary: j.coach_summary,
    }))
}

export async function buildJournalExportText(): Promise<string> {
  const [sessions, lickRows, jams, skills] = await Promise.all([
    listSessionsJournal(),
    getLicks(),
    listJamSnapshots(),
    getAllSkillNodes(),
  ])
  return formatJournalPlainText({
    exportedAt: new Date().toISOString(),
    sessions,
    licks: lickRows,
    jams,
    skills,
  })
}

export async function clearAllPracticeData(): Promise<void> {
  seedWebSkillNodes()
  sessionLog.length = 0
  sessionSongLog.length = 0
  licks.length = 0
  jamSnapshots.length = 0
  for (const n of DEFAULT_SKILL_NODES) {
    skillNodes.set(n.id, defaultSkillRow(n))
  }
  await idbClearPracticeStores(getHarmoniqIdbHandle())
  await flushSkillNodes()
}

export async function insertLickRow(input: LickInsertInput): Promise<void> {
  const row: LickRow = {
    id: input.id,
    song_title: input.song_title,
    artist: input.artist,
    key: input.key,
    scale: input.scale,
    position: input.position,
    tab_gp5_base64: input.tab_gp5_base64,
    audio_segment_path: input.audio_segment_path,
    coach_oneliner: input.coach_oneliner,
    technique_tags: input.technique_tags ?? [],
    user_annotations: input.user_annotations ?? [],
    date_saved: input.date_saved,
  }
  const i = licks.findIndex((x) => x.id === row.id)
  if (i >= 0) licks[i] = row
  else licks.push(row)
  await flushLicks()
}

export async function getLicks(): Promise<LickRow[]> {
  return [...licks].sort((a, b) => (a.date_saved < b.date_saved ? 1 : -1))
}

export async function getLickById(id: string): Promise<LickRow | null> {
  seedWebSkillNodes()
  return licks.find((x) => x.id === id) ?? null
}

export async function deleteLickById(id: string): Promise<void> {
  seedWebSkillNodes()
  const i = licks.findIndex((x) => x.id === id)
  if (i < 0) return
  licks.splice(i, 1)
  await flushLicks()
}

/** After `initDb`, restore last `LessonJSON` from IDB if store is still empty (web reload). */
export async function hydrateWebLessonStore(): Promise<void> {
  const lesson = await idbReadLessonCache(getHarmoniqIdbHandle())
  if (!lesson) return
  const { useLessonStore } = await import('@/src/stores/lessonStore')
  if (useLessonStore.getState().lesson != null) return
  useLessonStore.setState({ lesson, status: 'complete', error: null })
}
