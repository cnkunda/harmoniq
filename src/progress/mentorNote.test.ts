import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/src/api/analyze', () => ({
  loadLearningContextFromPrefs: vi.fn(),
  parseTasteProfileJson: vi.fn(),
}))
vi.mock('@/src/api/mentor', () => ({
  requestMentorNote: vi.fn(),
}))
vi.mock('@/src/db/client', () => ({
  getActivePracticePlanRow: vi.fn(),
  getAllSkillNodes: vi.fn(),
  getAppPref: vi.fn(),
  getLessonByJobId: vi.fn(),
  listJamSnapshots: vi.fn(),
  listLessonsJournal: vi.fn(),
  listPracticePlanCompletions: vi.fn(),
  listSessionsArchive: vi.fn(),
  listUserFeedback: vi.fn(),
  setAppPref: vi.fn(),
}))
vi.mock('@/src/stores/dnaStore', () => ({
  useDnaStore: {
    getState: () => ({ dna: null, refresh: vi.fn() }),
  },
}))

import type { MentorNote } from '@/src/api/mentor'
import { requestMentorNote } from '@/src/api/mentor'
import { loadLearningContextFromPrefs, parseTasteProfileJson } from '@/src/api/analyze'
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
import { PREF_MENTOR_STATE_JSON } from '@/src/db/schema'
import type { SessionArchiveRow } from '@/src/db/types'
import {
  loadMentorView,
  shouldAttemptMentor,
  shouldRefreshMentor,
  type MentorPersistedState,
} from './mentorNote'

const NOW = new Date('2026-10-26T12:00:00.000Z')
const DAY_MS = 24 * 60 * 60 * 1000

function note(generatedAt = NOW.toISOString()): MentorNote {
  return {
    headline: 'A steadier month',
    trajectory_summary: 'Timing improved while bends stayed uneven.',
    confidence: 'medium',
    plateau_diagnosis: null,
    next_month: [],
    next_songs: [],
    plan_guidance: 'The plan warms up before the section work.',
    generated_at: generatedAt,
    model: 'claude-haiku-4-5-20251001',
  }
}

function session(id: string, date: string): SessionArchiveRow {
  return {
    id,
    song_title: 'Blue in Green',
    artist: 'Miles Davis',
    section_label: 'Verse',
    date,
    coach_review: null,
    pitch_accuracy: 0.6,
    phrasing_score: 0.55,
    nodes_targeted: ['pitch_accuracy', 'phrasing', 'timing'],
    has_review_snapshot: false,
    waveform_user_path: null,
    waveform_ref_path: null,
    review_snapshot: null,
  }
}

function sessionsOverDays(days: number, count = 4): SessionArchiveRow[] {
  return Array.from({ length: count }, (_, index) => {
    const ms = NOW.getTime() - days * DAY_MS + index * Math.floor((days * DAY_MS) / count)
    return session(`session-${index}`, new Date(ms).toISOString())
  })
}

function setState(state: MentorPersistedState | null): void {
  vi.mocked(getAppPref).mockImplementation(async (key: string) => {
    if (key === PREF_MENTOR_STATE_JSON) return state ? JSON.stringify(state) : null
    return null
  })
}

function setDbSessions(sessions: SessionArchiveRow[]): void {
  vi.mocked(listSessionsArchive).mockResolvedValue(sessions)
  vi.mocked(listJamSnapshots).mockResolvedValue([])
  vi.mocked(listPracticePlanCompletions).mockResolvedValue([])
  vi.mocked(getActivePracticePlanRow).mockResolvedValue(null)
  vi.mocked(getAllSkillNodes).mockResolvedValue([])
  vi.mocked(listUserFeedback).mockResolvedValue([])
  vi.mocked(listLessonsJournal).mockResolvedValue([])
  vi.mocked(getLessonByJobId).mockResolvedValue(null)
  vi.mocked(parseTasteProfileJson).mockReturnValue(null)
  vi.mocked(loadLearningContextFromPrefs).mockResolvedValue(undefined)
}

function state(overrides: Partial<MentorPersistedState> = {}): MentorPersistedState {
  return {
    note: note(),
    generated_at: NOW.toISOString(),
    last_attempt_at: NOW.toISOString(),
    last_error: null,
    ...overrides,
  }
}

describe('mentorNote cadence', () => {
  it('keeps a fresh note without calling the API', async () => {
    setState(state())
    setDbSessions(sessionsOverDays(45))
    vi.mocked(requestMentorNote).mockResolvedValue(note())

    const view = await loadMentorView('plan', { now: NOW })

    expect(view.kind).toBe('ready')
    if (view.kind === 'ready') {
      expect(view.stale).toBe(false)
      expect(view.note.headline).toBe('A steadier month')
    }
    expect(requestMentorNote).not.toHaveBeenCalled()
  })

  it('generates and persists a note when the player is eligible', async () => {
    setState(null)
    setDbSessions(sessionsOverDays(45))
    vi.mocked(requestMentorNote).mockResolvedValue(note())

    const view = await loadMentorView('single', { now: NOW })

    expect(view.kind).toBe('ready')
    expect(requestMentorNote).toHaveBeenCalledTimes(1)
    if (view.kind === 'ready') {
      expect(view.note.headline).toBe('A steadier month')
      expect(view.trajectory.mode).toBe('single')
    }
    expect(setAppPref).toHaveBeenCalledWith(
      PREF_MENTOR_STATE_JSON,
      expect.stringContaining('A steadier month'),
    )
  })

  it('preserves the last note and reports a refresh failure', async () => {
    const staleNote = note(new Date(NOW.getTime() - 40 * DAY_MS).toISOString())
    setState(
      state({
        note: staleNote,
        generated_at: staleNote.generated_at,
        last_attempt_at: new Date(NOW.getTime() - 10 * DAY_MS).toISOString(),
      }),
    )
    setDbSessions(sessionsOverDays(45))
    vi.mocked(requestMentorNote).mockRejectedValue(new Error('Mentor is offline'))

    const view = await loadMentorView('plan', { now: NOW })

    expect(view.kind).toBe('ready')
    if (view.kind === 'ready') {
      expect(view.stale).toBe(true)
      expect(view.refreshError).toBe('Mentor is offline')
      expect(view.note).toStrictEqual(staleNote)
    }
    expect(setAppPref).toHaveBeenCalledWith(
      PREF_MENTOR_STATE_JSON,
      expect.stringContaining('Mentor is offline'),
    )
  })

  it('returns ineligible before 30 days and never calls the API', async () => {
    setState(null)
    setDbSessions(sessionsOverDays(10, 3))
    vi.mocked(requestMentorNote).mockResolvedValue(note())

    const view = await loadMentorView('plan', { now: NOW })

    expect(view.kind).toBe('ineligible')
    expect(requestMentorNote).not.toHaveBeenCalled()
  })

  it('throttles automatic retries after a failure', async () => {
    const staleNote = note(new Date(NOW.getTime() - 40 * DAY_MS).toISOString())
    setState(
      state({
        note: staleNote,
        generated_at: staleNote.generated_at,
        last_attempt_at: new Date(NOW.getTime() - 60 * 60 * 1000).toISOString(),
        last_error: 'Previous failure',
      }),
    )
    setDbSessions(sessionsOverDays(45))

    const view = await loadMentorView('plan', { now: NOW })

    expect(view.kind).toBe('ready')
    if (view.kind === 'ready') {
      expect(view.stale).toBe(true)
      expect(view.refreshError).toBe('Previous failure')
    }
    expect(requestMentorNote).not.toHaveBeenCalled()
  })

  it('gates refresh at 30 days and retry at 6 hours', () => {
    const fresh = state({ generated_at: new Date(NOW.getTime() - 29 * DAY_MS).toISOString() })
    expect(shouldRefreshMentor(fresh, NOW)).toBe(false)
    const stale = state({ generated_at: new Date(NOW.getTime() - 31 * DAY_MS).toISOString() })
    expect(shouldRefreshMentor(stale, NOW)).toBe(true)
    expect(shouldAttemptMentor(state({ last_attempt_at: new Date(NOW.getTime() - 5 * 60 * 60 * 1000).toISOString() }), NOW)).toBe(false)
    expect(shouldAttemptMentor(state({ last_attempt_at: new Date(NOW.getTime() - 7 * 60 * 60 * 1000).toISOString() }), NOW)).toBe(true)
  })
})

beforeEach(() => {
  vi.clearAllMocks()
})
