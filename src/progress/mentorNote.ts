import { loadLearningContextFromPrefs, parseTasteProfileJson } from '@/src/api/analyze'
import { requestMentorNote, type MentorLibrarySong, type MentorMode, type MentorNote, type MentorTrajectoryRequest } from '@/src/api/mentor'
import {
  getActivePracticePlanRow,
  getAllSkillNodes,
  getAppPref,
  getLessonByJobId,
  listJamSnapshots,
  listLessonsJournal,
  listPracticePlanCompletions,
  listSessionsArchive,
  listUserFeedback,
  setAppPref,
} from '@/src/db/client'
import { PREF_MENTOR_STATE_JSON, PREF_TASTE_PROFILE_JSON } from '@/src/db/schema'
import { extractTechniqueTagsFromSection } from '@/src/session/skillMutator'
import { useDnaStore } from '@/src/stores/dnaStore'
import {
  buildMentorTrajectory,
  MENTOR_REFRESH_DAYS,
  MENTOR_RETRY_THROTTLE_MS,
  type MentorTrajectoryBuildResult,
} from '@/src/progress/mentorTrajectory'

const DAY_MS = 24 * 60 * 60 * 1000
const LOG_PREFIX = '[Mentor]'

export interface MentorPersistedState {
  note: MentorNote | null
  generated_at: string | null
  last_attempt_at: string | null
  last_error: string | null
}

export type MentorView =
  | { kind: 'ineligible'; historyDays: number; evidenceCount: number }
  | {
      kind: 'ready'
      note: MentorNote
      trajectory: MentorTrajectoryRequest
      stale: boolean
      refreshError: string | null
    }
  | { kind: 'error'; message: string; historyDays: number; evidenceCount: number }

export interface MentorLoadOptions {
  force?: boolean
  now?: Date
}

function emptyState(): MentorPersistedState {
  return { note: null, generated_at: null, last_attempt_at: null, last_error: null }
}

function parseDateMs(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = new Date(value).getTime()
  return Number.isNaN(parsed) ? null : parsed
}

function isMentorNote(value: unknown): value is MentorNote {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const record = value as Record<string, unknown>
  return (
    typeof record.headline === 'string' &&
    typeof record.trajectory_summary === 'string' &&
    typeof record.generated_at === 'string' &&
    Array.isArray(record.next_month) &&
    Array.isArray(record.next_songs)
  )
}

function parseState(raw: string | null): MentorPersistedState {
  if (!raw?.trim()) return emptyState()
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      console.warn(`${LOG_PREFIX} persisted state was not an object; ignoring`)
      return emptyState()
    }
    const record = parsed as Record<string, unknown>
    return {
      note: isMentorNote(record.note) ? record.note : null,
      generated_at: typeof record.generated_at === 'string' ? record.generated_at : null,
      last_attempt_at: typeof record.last_attempt_at === 'string' ? record.last_attempt_at : null,
      last_error: typeof record.last_error === 'string' ? record.last_error : null,
    }
  } catch (error) {
    console.warn(`${LOG_PREFIX} could not parse persisted state`, error)
    return emptyState()
  }
}

export async function loadMentorState(): Promise<MentorPersistedState> {
  return parseState(await getAppPref(PREF_MENTOR_STATE_JSON))
}

export async function saveMentorState(state: MentorPersistedState): Promise<void> {
  await setAppPref(PREF_MENTOR_STATE_JSON, JSON.stringify(state))
}

/** Monthly cadence: a note older than 30 days is stale. */
export function shouldRefreshMentor(state: MentorPersistedState, now: Date = new Date()): boolean {
  if (state.note == null) return true
  const generatedAt = parseDateMs(state.generated_at) ?? parseDateMs(state.note.generated_at)
  if (generatedAt == null) return true
  return now.getTime() - generatedAt >= MENTOR_REFRESH_DAYS * DAY_MS
}

/** After a failure, wait before auto-retrying so Progress focus does not hammer the API. */
export function shouldAttemptMentor(state: MentorPersistedState, now: Date = new Date()): boolean {
  const lastAttempt = parseDateMs(state.last_attempt_at)
  if (lastAttempt == null) return true
  return now.getTime() - lastAttempt >= MENTOR_RETRY_THROTTLE_MS
}

async function loadLibrarySongs(): Promise<MentorLibrarySong[]> {
  const rows = await listLessonsJournal()
  const recent = [...rows]
    .sort((a, b) => {
      const aTs = parseDateMs(a.analyzed_at) ?? 0
      const bTs = parseDateMs(b.analyzed_at) ?? 0
      return bTs - aTs
    })
    .slice(0, 8)

  const songs = await Promise.all(
    recent.map(async (row): Promise<MentorLibrarySong | null> => {
      let lesson = null
      try {
        lesson = await getLessonByJobId(row.job_id)
      } catch (error) {
        console.warn(`${LOG_PREFIX} could not load lesson detail for job ${row.job_id}`, error)
      }
      const title = row.song_title?.trim() || lesson?.song_title?.trim() || ''
      if (!title) return null
      const techniques = new Set<string>()
      for (const section of lesson?.sections ?? []) {
        for (const tag of extractTechniqueTagsFromSection(section)) techniques.add(tag)
      }
      return {
        job_id: row.job_id,
        title,
        artist: row.artist?.trim() || lesson?.artist?.trim() || null,
        style_label: lesson?.style_label?.trim() || null,
        tempo: lesson?.tempo ?? null,
        techniques: [...techniques].slice(0, 6),
      }
    }),
  )
  return songs.filter((song): song is MentorLibrarySong => song != null)
}

async function prepareMentorData(mode: MentorMode, now: Date): Promise<MentorTrajectoryBuildResult> {
  const [sessions, jams, completions, activePlan, skillNodes, feedback, tasteRaw, learningContext] =
    await Promise.all([
      listSessionsArchive(),
      listJamSnapshots(),
      listPracticePlanCompletions(),
      getActivePracticePlanRow(),
      getAllSkillNodes(),
      listUserFeedback(),
      getAppPref(PREF_TASTE_PROFILE_JSON),
      loadLearningContextFromPrefs(),
    ])

  const taste = parseTasteProfileJson(tasteRaw)
  let dna = useDnaStore.getState().dna
  if (dna == null) {
    try {
      await useDnaStore.getState().refresh()
      dna = useDnaStore.getState().dna
    } catch (error) {
      console.warn(`${LOG_PREFIX} could not refresh Riff DNA`, error)
    }
  }

  const librarySongs: MentorLibrarySong[] = []
  return buildMentorTrajectory({
    mode,
    now,
    sessions,
    jams,
    completions,
    activePlan,
    skillNodes,
    feedback,
    dna,
    taste,
    learningContext: learningContext ?? null,
    librarySongs,
    tasteSongCandidates: taste?.song_candidates ?? [],
  })
}

/** Load, gate, and (when needed) refresh the mentor note. Never mutates plans. */
export async function loadMentorView(mode: MentorMode, options: MentorLoadOptions = {}): Promise<MentorView> {
  const now = options.now ?? new Date()
  const state = await loadMentorState()

  let prepared: MentorTrajectoryBuildResult
  try {
    prepared = await prepareMentorData(mode, now)
  } catch (error) {
    console.error(`${LOG_PREFIX} could not read practice history`, error)
    return {
      kind: 'error',
      message: 'Could not read your practice history. Try again in a moment.',
      historyDays: 0,
      evidenceCount: 0,
    }
  }

  const { eligible, historyDays, evidenceCount, payload } = prepared
  const hasNote = state.note != null
  const stale = shouldRefreshMentor(state, now)

  if (hasNote && !stale) {
    return { kind: 'ready', note: state.note!, trajectory: payload, stale: false, refreshError: null }
  }

  if (!eligible) {
    if (hasNote) {
      return {
        kind: 'ready',
        note: state.note!,
        trajectory: payload,
        stale: true,
        refreshError: state.last_error,
      }
    }
    return { kind: 'ineligible', historyDays, evidenceCount }
  }

  const canAttempt = options.force === true || shouldAttemptMentor(state, now)
  if (!canAttempt) {
    if (hasNote) {
      return {
        kind: 'ready',
        note: state.note!,
        trajectory: payload,
        stale: true,
        refreshError: state.last_error,
      }
    }
    return {
      kind: 'error',
      message: state.last_error ?? 'Mentor is unavailable right now. Try again later.',
      historyDays,
      evidenceCount,
    }
  }

  try {
    let librarySongs: MentorLibrarySong[] = []
    try {
      librarySongs = await loadLibrarySongs()
    } catch (error) {
      console.warn(`${LOG_PREFIX} could not load library songs`, error)
    }
    const requestPayload = { ...payload, library_songs: librarySongs }
    const note = await requestMentorNote(requestPayload)
    const nextState: MentorPersistedState = {
      note,
      generated_at: note.generated_at,
      last_attempt_at: now.toISOString(),
      last_error: null,
    }
    try {
      await saveMentorState(nextState)
    } catch (error) {
      console.error(`${LOG_PREFIX} could not persist mentor note`, error)
    }
    return { kind: 'ready', note, trajectory: requestPayload, stale: false, refreshError: null }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Mentor request failed.'
    console.error(`${LOG_PREFIX} mentor request failed`, error)
    try {
      await saveMentorState({ ...state, last_attempt_at: now.toISOString(), last_error: message })
    } catch (persistError) {
      console.error(`${LOG_PREFIX} could not persist mentor failure`, persistError)
    }
    if (hasNote) {
      return {
        kind: 'ready',
        note: state.note!,
        trajectory: payload,
        stale: true,
        refreshError: message,
      }
    }
    return { kind: 'error', message, historyDays, evidenceCount }
  }
}
