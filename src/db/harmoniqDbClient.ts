import type {
    AnalyticsEventRow,
    CommitScoredSessionInput,
    CommitScoredSessionResult,
    FinalizePracticePlanInput,
    HomeSuggestion,
    JamSnapshotInsertInput,
    JamSnapshotRow,
    GhostReferenceRow,
    LickInsertInput,
    LickRow,
    LatestSessionSongRow,
    LessonListRow,
    NodeSessionSnippet,
    PracticePlanCompletionInsertInput,
    PracticePlanCompletionRow,
    PracticePlanRow,
    PracticePlanStartInput,
    PracticePlanStateUpdate,
    PracticePlanStatus,
    SessionArchiveRow,
    SessionInsertInput,
    SessionJournalRow,
    SkillNodeRow,
    UserFeedbackInsertInput,
    UserFeedbackRow,
    UserFeedbackStats,
} from '@/src/db/types'
import type { LessonJSON, TasteProfilePayload } from '@/src/types'

/**
 * Shared repository surface for `client.native` (SQLite) and `client.web` (IndexedDB + memory).
 * Metro picks the platform implementation; this type keeps APIs aligned (PRIORITIES §38).
 */
export interface HarmoniqDbClient {
  initDb(): Promise<void>
  insertSessionRow(input: SessionInsertInput): Promise<void>
  getSessionCount(): Promise<number>
  listSessionsJournal(): Promise<SessionJournalRow[]>
  /** Newest-first rows including `review_snapshot` (commit 74 DNA). */
  listSessionsArchive(): Promise<SessionArchiveRow[]>
  getSessionById(id: string): Promise<SessionArchiveRow | null>
  /** Commit 75: latest ghost take for a lesson section. */
  getLatestGhostReference(jobId: string, sectionIndex: number): Promise<GhostReferenceRow | null>
  getLatestSessionSnippetForNode(nodeId: string): Promise<NodeSessionSnippet | null>
  getAllSkillNodes(): Promise<SkillNodeRow[]>
  getAppPref(key: string): Promise<string | null>
  setAppPref(key: string, value: string): Promise<void>
  getOnboardingComplete(): Promise<boolean>
  setOnboardingComplete(): Promise<void>
  commitPlacementOnboarding(aggregatedNodeScores: Record<string, number>): Promise<void>
  /** Commit 69: persist derived taste + experience-tier skill weights after taste quiz. */
  commitTasteQuizProfile(
    taste: TasteProfilePayload,
    experienceLevel: 'beginner' | 'intermediate' | 'advanced',
  ): Promise<void>
  getLatestSessionWithSong(): Promise<LatestSessionSongRow | null>
  getHomeSuggestion(): Promise<HomeSuggestion>
  /** Commit 164: atomic + idempotent scored-session commit (session row + mastery + ledger). */
  commitScoredSession(input: CommitScoredSessionInput): Promise<CommitScoredSessionResult>
  insertJamSnapshotRow(input: JamSnapshotInsertInput): Promise<void>
  listJamSnapshots(): Promise<JamSnapshotRow[]>
  /** Commit 160: persist the background summary result for an existing snapshot. */
  updateJamSnapshotSummary(
    id: string,
    input: {
      summary_bundle_json: string | null
      coach_summary: string
      summary_status: 'pending' | 'ready' | 'failed' | 'skipped'
    },
  ): Promise<void>
  insertPracticePlanCompletionRow(input: PracticePlanCompletionInsertInput): Promise<void>
  /** Commit 164: completion history + session row + plan status in one transaction. */
  finalizePracticePlan(input: FinalizePracticePlanInput): Promise<void>
  listPracticePlanCompletions(): Promise<PracticePlanCompletionRow[]>
  /** Commit 162: start a plan, abandoning any older active row. */
  startActivePracticePlanRow(input: PracticePlanStartInput): Promise<void>
  getActivePracticePlanRow(): Promise<PracticePlanRow | null>
  updatePracticePlanRowState(planId: string, update: PracticePlanStateUpdate): Promise<void>
  markPracticePlanStatus(planId: string, status: PracticePlanStatus): Promise<void>
  clearPracticePlans(): Promise<void>
  buildJournalExportText(): Promise<string>
  clearAllPracticeData(): Promise<void>
  insertLickRow(input: LickInsertInput): Promise<void>
  getLicks(): Promise<LickRow[]>
  getLickById(id: string): Promise<LickRow | null>
  deleteLickById(id: string): Promise<void>
  upsertLessonFromAnalysis(lesson: LessonJSON): Promise<void>
  listLessonsJournal(): Promise<LessonListRow[]>
  getLessonByJobId(jobId: string): Promise<LessonJSON | null>
  deleteLessonByJobId(jobId: string): Promise<void>
  /** Web: hydrate Zustand from IDB lesson cache. Native: no-op. */
  hydrateWebLessonStore(): Promise<void>
  /** Commit 159: latest feedback per (job, type, event), newest first. */
  upsertUserFeedback(input: UserFeedbackInsertInput): Promise<UserFeedbackRow>
  listUserFeedback(): Promise<UserFeedbackRow[]>
  listUserFeedbackForJob(jobId: string): Promise<UserFeedbackRow[]>
  deleteUserFeedback(id: string): Promise<void>
  getUserFeedbackStats(): Promise<UserFeedbackStats>
  /** Commit 161: insert/replace local analytics rows. */
  insertAnalyticsEvents(rows: AnalyticsEventRow[]): Promise<void>
  /** Commit 161: newest-first local analytics rows. */
  listAnalyticsEvents(): Promise<AnalyticsEventRow[]>
}
