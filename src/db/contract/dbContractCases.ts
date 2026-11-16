/**
 * Shared DB contract cases run against both persistence clients (Commit 17).
 * Framework-free by design: the native suite executes these in Vitest against
 * `client.native` (SQLite via node:sqlite), and the web suite executes the same
 * list in Chromium against `client.web` (IndexedDB). No test-framework imports
 * are allowed here because the browser bundle cannot include them.
 *
 * Every case is self-contained: it starts by wiping practice state
 * (`clearAllPracticeData`) so cases never depend on execution order.
 */

import type { ContractAssert, ContractCaseResult } from '@/src/db/contract/contractAssert'
import { createContractAssert } from '@/src/db/contract/contractAssert'
import type { AnalyticsEventType } from '@/src/analytics/types'
import type { LessonJSON } from '@/src/types'
import type {
    AnalyticsEventRow,
    CommitScoredSessionInput,
    JamSnapshotInsertInput,
    LickInsertInput,
    SessionInsertInput,
    UserFeedbackInsertInput,
} from '@/src/db/types'
import type { HarmoniqDbClient } from '@/src/db/harmoniqDbClient'

export type DbContractCase = {
  name: string
  run(client: HarmoniqDbClient, assert: ContractAssert): Promise<void>
}

const D_OLD = '2026-01-01T10:00:00.000Z'
const D_MID = '2026-01-02T10:00:00.000Z'
const D_NEW = '2026-01-03T10:00:00.000Z'
const T_SAME = '2026-03-01T00:00:00.000Z'

function sessionInput(id: string, date: string, overrides: Partial<SessionInsertInput> = {}): SessionInsertInput {
  return {
    id,
    song_title: null,
    artist: null,
    section_label: 'Verse',
    date,
    coach_review: null,
    pitch_accuracy: 0.8,
    phrasing_score: 0.7,
    nodes_targeted: ['pitch_accuracy'],
    ...overrides,
  }
}

function scoredSessionInput(sessionId: string, date: string): CommitScoredSessionInput {
  return {
    session: sessionInput(sessionId, date, {
      song_title: 'Contract Song',
      artist: 'Contractor',
      nodes_targeted: ['pitch_accuracy', 'phrasing', 'timing'],
    }),
    reviewUpdates: {
      node_scores: { pitch_accuracy: 1, phrasing: 1, timing: 1 },
      targeted_node_ids: ['pitch_accuracy', 'phrasing', 'timing'],
      session_accuracy01: 1,
      session_timing_stability01: 1,
    },
    beats: [],
    section: null,
    applyTechniqueEma: false,
  }
}

function jamInput(id: string, date: string, overrides: Partial<JamSnapshotInsertInput> = {}): JamSnapshotInsertInput {
  return {
    id,
    date,
    duration_seconds: 120,
    scale_position_map: { pc_C: 0.5 },
    pitch_class_weight_map: { pc_C: 0.5 },
    position_weight_map: null,
    recurring_gestures: ['bend'],
    coach_summary: 'kept the pulse',
    reliability_tags: ['timing'],
    ...overrides,
  }
}

function lickInput(id: string, date: string, overrides: Partial<LickInsertInput> = {}): LickInsertInput {
  return {
    id,
    song_title: 'Lick Song',
    artist: null,
    key: 'C',
    scale: 'major_pentatonic',
    position: 'box1',
    tab_gp5_base64: 'Z3A1',
    audio_segment_path: null,
    stems_json: null,
    coach_oneliner: 'nice bend',
    technique_tags: ['bending'],
    user_annotations: [{ bar: 3, text: 'slow down' }],
    date_saved: date,
    ...overrides,
  }
}

function feedbackInput(
  id: string,
  jobId: string,
  feedbackType: UserFeedbackInsertInput['feedback_type'],
  eventIndex: number,
  overrides: Partial<UserFeedbackInsertInput> = {},
): UserFeedbackInsertInput {
  return {
    id,
    job_id: jobId,
    song_id: 'song-1',
    user_id: 'user-1',
    timestamp: T_SAME,
    feedback_type: feedbackType,
    event_index: eventIndex,
    original_value: 'Am',
    corrected_value: 'C',
    reason: null,
    ...overrides,
  }
}

function analyticsRow(id: string, eventType: AnalyticsEventType, overrides: Partial<AnalyticsEventRow> = {}): AnalyticsEventRow {
  return {
    id,
    user_id: 'user-1',
    event_type: eventType,
    payload_json: '{"step":"tune"}',
    timestamp: T_SAME,
    ...overrides,
  }
}

function lessonFixture(jobId: string, songTitle: string): LessonJSON {
  return {
    job_id: jobId,
    song_title: songTitle,
    artist: 'Contractor',
    source_url: `https://example.com/${jobId}`,
    sections: [{ label: 'Intro' }, { label: 'Verse' }],
  }
}

export const DB_CONTRACT_CASES: DbContractCase[] = [
  {
    name: 'app prefs roundtrip',
    async run(client, assert) {
      await client.clearAllPracticeData()
      assert.equal(await client.getAppPref('contract_missing'), null, 'unknown pref returns null')
      await client.setAppPref('contract_pref', 'one')
      assert.equal(await client.getAppPref('contract_pref'), 'one', 'set then get')
      await client.setAppPref('contract_pref', 'two')
      assert.equal(await client.getAppPref('contract_pref'), 'two', 'overwrite wins')
    },
  },
  {
    name: 'onboarding flag persists',
    async run(client, assert) {
      await client.clearAllPracticeData()
      assert.equal(await client.getOnboardingComplete(), false, 'fresh db has onboarding incomplete')
      await client.setOnboardingComplete()
      assert.equal(await client.getOnboardingComplete(), true, 'flag persists after set')
    },
  },
  {
    name: 'session journal + archive ordering and snapshot passthrough',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.insertSessionRow(sessionInput('s-old', D_OLD))
      await client.insertSessionRow(
        sessionInput('s-mid', D_MID, {
          song_title: 'Mid Song',
          review_snapshot: '{"accuracy":0.9}',
          nodes_targeted: ['timing'],
        }),
      )
      await client.insertSessionRow(sessionInput('s-new', D_NEW, { mood: 'focused' }))
      assert.equal(await client.getSessionCount(), 3, 'three sessions stored')

      const journal = await client.listSessionsJournal()
      assert.deepEqual(
        journal.map((r) => r.id),
        ['s-new', 's-mid', 's-old'],
        'journal is newest-first by date',
      )
      assert.deepEqual(journal[1]?.nodes_targeted, ['timing'], 'nodes_targeted roundtrip')
      assert.equal(journal[0]?.has_review_snapshot, false, 'no snapshot flag')
      assert.equal(journal[1]?.has_review_snapshot, true, 'snapshot flag')
      assert.equal(journal[0]?.mood, 'focused', 'mood roundtrip')

      const archive = await client.listSessionsArchive()
      assert.equal(archive[1]?.review_snapshot, '{"accuracy":0.9}', 'archive snapshot passthrough')

      const byId = await client.getSessionById('s-mid')
      assert.equal(byId?.song_title, 'Mid Song', 'getSessionById finds row')
      assert.equal(byId?.review_snapshot, '{"accuracy":0.9}', 'getSessionById snapshot')
      assert.equal(await client.getSessionById('missing'), null, 'getSessionById miss returns null')
    },
  },
  {
    name: 'session upsert follows date order for latest-song lookup',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.insertSessionRow(sessionInput('s-newer', D_MID, { song_title: 'Newer Song' }))
      await client.insertSessionRow(sessionInput('s-older', D_OLD, { song_title: 'Older Song' }))
      assert.equal(
        (await client.getLatestSessionWithSong())?.song_title,
        'Newer Song',
        'older-date insert must not shadow the newest song',
      )

      await client.insertSessionRow(sessionInput('s-newer', D_NEW, { song_title: 'Newer Song' }))
      assert.equal(await client.getSessionCount(), 2, 'replace keeps row count stable')
      assert.equal(
        (await client.getLatestSessionWithSong())?.song_title,
        'Newer Song',
        'replaced row stays newest',
      )
    },
  },
  {
    name: 'node snippet returns newest session targeting the node',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.insertSessionRow(sessionInput('s-timing', D_OLD, { nodes_targeted: ['timing'] }))
      await client.insertSessionRow(sessionInput('s-pitch-old', D_MID, { coach_review: 'older pitch take' }))
      await client.insertSessionRow(sessionInput('s-pitch-new', D_NEW, { coach_review: 'latest pitch take' }))

      const pitch = await client.getLatestSessionSnippetForNode('pitch_accuracy')
      assert.equal(pitch?.date, D_NEW, 'pitch snippet is newest')
      assert.equal(pitch?.coach_review, 'latest pitch take', 'snippet review matches newest row')

      const timing = await client.getLatestSessionSnippetForNode('timing')
      assert.equal(timing?.date, D_OLD, 'timing snippet falls back to its only session')
      assert.equal(await client.getLatestSessionSnippetForNode('vibrato_control'), null, 'untracked node returns null')
    },
  },
  {
    name: 'scored session commit is idempotent and updates mastery',
    async run(client, assert) {
      await client.clearAllPracticeData()
      const scoreOf = async (): Promise<number> =>
        (await client.getAllSkillNodes()).find((n) => n.id === 'pitch_accuracy')?.score ?? 0

      const first = await client.commitScoredSession(scoredSessionInput('cs-1', D_OLD))
      assert.equal(first.applied, true, 'first commit applies')
      const afterFirst = await scoreOf()
      assert.truthy(afterFirst > 0, 'skill score rises after commit')
      assert.equal(await client.getSessionCount(), 1, 'one session stored')

      const replay = await client.commitScoredSession(scoredSessionInput('cs-1', D_OLD))
      assert.equal(replay.applied, false, 'replay is a no-op')
      assert.equal(await scoreOf(), afterFirst, 'score unchanged on replay')
      assert.equal(await client.getSessionCount(), 1, 'replay adds no session')

      const second = await client.commitScoredSession(scoredSessionInput('cs-2', D_NEW))
      assert.equal(second.applied, true, 'different session id applies again')
      assert.equal(await client.getSessionCount(), 2, 'second session stored')
    },
  },
  {
    name: 'ghost reference lookup',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.insertSessionRow(
        sessionInput('s-ghost', D_OLD, {
          job_id: 'job-1',
          section_index: 2,
          is_ghost_reference: true,
          ghost_anchor_sec: 12.5,
          ghost_audio_base64: 'QUJD',
          ghost_recording_mime: 'audio/webm',
        }),
      )
      await client.insertSessionRow(
        sessionInput('s-later', D_NEW, { job_id: 'job-1', section_index: 2, is_ghost_reference: false }),
      )
      const ghost = await client.getLatestGhostReference('job-1', 2)
      assert.equal(ghost?.id, 's-ghost', 'returns the ghost take even when a newer take exists')
      assert.equal(ghost?.ghost_anchor_sec, 12.5, 'anchor roundtrip')
      assert.equal(ghost?.ghost_recording_mime, 'audio/webm', 'mime roundtrip')
      assert.equal(await client.getLatestGhostReference('job-1', 0), null, 'other section returns null')
      assert.equal(await client.getLatestGhostReference('   ', 2), null, 'blank job id returns null')
    },
  },
  {
    name: 'jam snapshot upsert replaces duplicate id and tolerates null arrays',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.insertJamSnapshotRow(jamInput('jam-a', D_MID))
      await client.insertJamSnapshotRow(jamInput('jam-b', D_OLD, { reliability_tags: null, position_weight_map: null }))
      const listed = await client.listJamSnapshots()
      assert.deepEqual(
        listed.map((j) => j.id),
        ['jam-a', 'jam-b'],
        'jam list is newest-first by date',
      )
      assert.deepEqual(listed[1]?.reliability_tags, [], 'null reliability_tags degrades to []')
      assert.deepEqual(listed[1]?.position_weight_map, {}, 'null position map degrades to {}')

      await client.insertJamSnapshotRow(jamInput('jam-a', D_MID, { coach_summary: 'updated summary' }))
      const afterUpsert = await client.listJamSnapshots()
      assert.equal(afterUpsert.length, 2, 'duplicate jam id replaces instead of duplicating')
      assert.equal(
        afterUpsert.find((j) => j.id === 'jam-a')?.coach_summary,
        'updated summary',
        'replaced row carries new payload',
      )
    },
  },
  {
    name: 'jam summary update and missing-id rejection',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.insertJamSnapshotRow(jamInput('jam-a', D_MID, { summary_status: 'pending' }))
      await client.updateJamSnapshotSummary('jam-a', {
        summary_bundle_json: '{"v":1}',
        coach_summary: 'ready summary',
        summary_status: 'ready',
      })
      const row = (await client.listJamSnapshots()).find((j) => j.id === 'jam-a')
      assert.equal(row?.summary_status, 'ready', 'summary status updated')
      assert.equal(row?.coach_summary, 'ready summary', 'summary text updated')
      assert.equal(row?.summary_bundle_json, '{"v":1}', 'bundle json updated')
      await assert.rejects(
        () =>
          client.updateJamSnapshotSummary('missing', {
            summary_bundle_json: null,
            coach_summary: 'x',
            summary_status: 'failed',
          }),
        'not found',
      )
    },
  },
  {
    name: 'practice plan lifecycle',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.startActivePracticePlanRow({
        plan_id: 'plan-1',
        plan_json: '{"slots":1}',
        current_slot_index: 0,
      })
      await client.startActivePracticePlanRow({ plan_id: 'plan-2', plan_json: '{"slots":2}', current_slot_index: 1 })
      let active = await client.getActivePracticePlanRow()
      assert.equal(active?.plan_id, 'plan-2', 'starting a plan abandons the older active plan')
      assert.equal(active?.current_slot_index, 1, 'start slot index persists')

      await client.updatePracticePlanRowState('plan-2', { current_slot_index: 2, slot_results_json: '[{"i":0}]' })
      active = await client.getActivePracticePlanRow()
      assert.equal(active?.current_slot_index, 2, 'state update persists')
      assert.equal(active?.slot_results_json, '[{"i":0}]', 'slot results update persists')

      await client.markPracticePlanStatus('plan-2', 'completed')
      assert.equal(await client.getActivePracticePlanRow(), null, 'completed plan is no longer active')
      await client.clearPracticePlans()
      assert.equal(await client.getActivePracticePlanRow(), null, 'cleared plans leave nothing active')
    },
  },
  {
    name: 'plan finalize is idempotent',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.startActivePracticePlanRow({ plan_id: 'plan-f', plan_json: '{"slots":1}', current_slot_index: 0 })
      const finalize = {
        plan_id: 'plan-f',
        completion: { id: 'comp-1', completed_at: D_NEW, plan_json: '{"slots":1}' },
        session: sessionInput('s-final', D_NEW, { song_title: 'Final Song' }),
      }
      await client.finalizePracticePlan(finalize)
      const completions = await client.listPracticePlanCompletions()
      assert.equal(completions.length, 1, 'one completion recorded')
      assert.equal(await client.getSessionCount(), 1, 'finalize stores its session row')
      assert.equal(await client.getActivePracticePlanRow(), null, 'finalized plan is not active')

      await client.finalizePracticePlan({
        ...finalize,
        completion: { id: 'comp-2', completed_at: D_NEW, plan_json: '{"slots":1}' },
      })
      assert.equal((await client.listPracticePlanCompletions()).length, 1, 'second finalize is a no-op')
    },
  },
  {
    name: 'licks crud and ordering',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.insertLickRow(lickInput('lick-new', D_MID))
      await client.insertLickRow(lickInput('lick-old', D_OLD))
      const licks = await client.getLicks()
      assert.deepEqual(
        licks.map((l) => l.id),
        ['lick-new', 'lick-old'],
        'licks are newest-first by date_saved',
      )
      const byId = await client.getLickById('lick-old')
      assert.equal(byId?.coach_oneliner, 'nice bend', 'lick row roundtrip')
      assert.deepEqual(byId?.technique_tags, ['bending'], 'technique tags roundtrip')
      assert.deepEqual(byId?.user_annotations, [{ bar: 3, text: 'slow down' }], 'annotations roundtrip')

      await client.insertLickRow(lickInput('lick-new', D_MID, { coach_oneliner: 'edited' }))
      assert.equal((await client.getLicks()).length, 2, 'same-id lick upsert replaces')
      assert.equal((await client.getLickById('lick-new'))?.coach_oneliner, 'edited', 'edited lick persisted')

      await client.deleteLickById('lick-old')
      assert.equal((await client.getLicks()).length, 1, 'delete removes the lick')
      assert.equal(await client.getLickById('lick-old'), null, 'deleted lick lookup returns null')
    },
  },
  {
    name: 'lessons crud roundtrip',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.upsertLessonFromAnalysis(lessonFixture('job-a', 'Lesson A'))
      await new Promise((resolve) => setTimeout(resolve, 5))
      await client.upsertLessonFromAnalysis(lessonFixture('job-b', 'Lesson B'))
      const listed = await client.listLessonsJournal()
      assert.equal(listed.length, 2, 'two lessons stored')
      assert.equal(listed[0]?.job_id, 'job-b', 'lessons are newest-analyzed-first')
      assert.equal(listed[0]?.section_count, 2, 'section count derived from lesson')

      const loaded = await client.getLessonByJobId('job-a')
      assert.equal(loaded?.song_title, 'Lesson A', 'lesson json roundtrip title')
      assert.equal(loaded?.artist, 'Contractor', 'lesson json roundtrip artist')
      assert.equal(loaded?.sections?.length, 2, 'lesson json roundtrip sections')

      await client.upsertLessonFromAnalysis({ ...lessonFixture('job-b', 'Lesson B v2') })
      assert.equal((await client.listLessonsJournal()).length, 2, 'same-job upsert replaces')
      assert.equal((await client.getLessonByJobId('job-b'))?.song_title, 'Lesson B v2', 'replaced lesson json')

      await client.upsertLessonFromAnalysis({ ...lessonFixture('lick-x', 'Not a lesson') })
      assert.equal((await client.listLessonsJournal()).length, 2, 'lick-prefixed job ids are ignored')

      await client.deleteLessonByJobId('job-a')
      assert.equal(await client.getLessonByJobId('job-a'), null, 'deleted lesson returns null')
      assert.equal((await client.listLessonsJournal()).length, 1, 'delete shrinks the catalog')
    },
  },
  {
    name: 'feedback upsert replaces by key and orders deterministically',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.upsertUserFeedback(feedbackInput('fb-1', 'job-j', 'chord_correction', 0))
      await client.upsertUserFeedback(
        feedbackInput('fb-2', 'job-j', 'chord_correction', 0, { corrected_value: 'Dm' }),
      )
      assert.equal((await client.listUserFeedback()).length, 1, 'same (job,type,event) upserts replace')

      await client.upsertUserFeedback(feedbackInput('fb-3', 'job-j', 'note_correction', 1))
      const all = await client.listUserFeedback()
      assert.deepEqual(
        all.map((f) => f.id),
        ['fb-3', 'fb-2'],
        'equal timestamps fall back to deterministic id tie-break',
      )
      const forJob = await client.listUserFeedbackForJob('job-j')
      assert.deepEqual(
        forJob.map((f) => f.id),
        ['fb-3', 'fb-2'],
        'per-job listing matches global ordering',
      )
      assert.equal((await client.listUserFeedbackForJob('   ')).length, 0, 'blank job id returns none')

      const stats = await client.getUserFeedbackStats()
      assert.equal(stats.total, 2, 'stats total counts rows')
      assert.equal(stats.chord_corrections, 1, 'stats count chord corrections')
      assert.equal(stats.note_corrections, 1, 'stats count note corrections')

      await client.deleteUserFeedback('fb-2')
      assert.equal((await client.listUserFeedback()).length, 1, 'delete removes one row')
    },
  },
  {
    name: 'analytics upsert by id with newest-first tie-break',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.insertAnalyticsEvents([
        analyticsRow('evt-a', 'session_start'),
        analyticsRow('evt-b', 'session_complete', { payload_json: '{"duration_sec":60}' }),
      ])
      const listed = await client.listAnalyticsEvents()
      assert.deepEqual(
        listed.map((e) => e.id),
        ['evt-b', 'evt-a'],
        'equal timestamps order by id descending',
      )

      await client.insertAnalyticsEvents([analyticsRow('evt-a', 'session_start', { payload_json: '{"step":"play"}' })])
      const afterUpsert = await client.listAnalyticsEvents()
      assert.equal(afterUpsert.length, 2, 'same-id event replaces instead of duplicating')
      assert.equal(
        afterUpsert.find((e) => e.id === 'evt-a')?.payload_json,
        '{"step":"play"}',
        'replaced event payload persisted',
      )
    },
  },
  {
    name: 'clearAllPracticeData resets practice state',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.insertSessionRow(sessionInput('s-x', D_NEW, { song_title: 'Clear Song' }))
      await client.insertLickRow(lickInput('lick-x', D_NEW))
      await client.insertJamSnapshotRow(jamInput('jam-x', D_NEW))
      await client.insertPracticePlanCompletionRow({ id: 'comp-x', completed_at: D_NEW, plan_json: '{}' })
      await client.upsertUserFeedback(feedbackInput('fb-x', 'job-x', 'wrong_chord', 0))
      await client.insertAnalyticsEvents([analyticsRow('evt-x', 'jam_complete')])
      await client.commitScoredSession(scoredSessionInput('cs-x', D_NEW))

      await client.clearAllPracticeData()

      assert.equal(await client.getSessionCount(), 0, 'sessions cleared')
      assert.equal((await client.getLicks()).length, 0, 'licks cleared')
      assert.equal((await client.listJamSnapshots()).length, 0, 'jams cleared')
      assert.equal((await client.listPracticePlanCompletions()).length, 0, 'plan completions cleared')
      assert.equal((await client.listUserFeedback()).length, 0, 'feedback cleared')
      assert.equal((await client.listAnalyticsEvents()).length, 0, 'analytics cleared')
      assert.equal(await client.getLatestSessionWithSong(), null, 'latest-song lookup is empty after clear')
      const nodes = await client.getAllSkillNodes()
      assert.equal(nodes.length, 5, 'default skill nodes still seeded')
      assert.truthy(nodes.every((n) => n.score === 0 && n.sessions_count === 0), 'skill nodes reset to zero')
    },
  },
  {
    name: 'home suggestion ready path',
    async run(client, assert) {
      await client.clearAllPracticeData()
      await client.insertSessionRow(sessionInput('s-home', D_NEW, { song_title: 'Ready Song' }))
      const suggestion = await client.getHomeSuggestion()
      assert.equal(suggestion.kind, 'ready', 'song + due node yields ready suggestion')
      if (suggestion.kind !== 'ready') throw new Error('expected ready suggestion')
      assert.equal(suggestion.song.song_title, 'Ready Song', 'suggestion carries the latest song')
      assert.equal(suggestion.node.id, 'bend_accuracy', 'null next_review_date sorts first, tie-break by id')
    },
  },
]

/**
 * Runs every contract case against `client`, collecting one result per case
 * instead of throwing on first failure so the web harness can report all gaps.
 */
export async function runDbContractCases(client: HarmoniqDbClient): Promise<ContractCaseResult[]> {
  const results: ContractCaseResult[] = []
  for (const testCase of DB_CONTRACT_CASES) {
    const assert = createContractAssert()
    try {
      await testCase.run(client, assert)
      results.push({ name: testCase.name, passed: true, error: null })
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      console.log(`[dbContract] case failed: ${testCase.name} — ${error}`)
      results.push({ name: testCase.name, passed: false, error })
    }
  }
  return results
}
