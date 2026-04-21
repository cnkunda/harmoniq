import type {
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
    ReviewSkillUpdateInput,
    SessionArchiveRow,
    SessionInsertInput,
    SessionJournalRow,
    SkillNodeRow,
    SkillSessionMutationRow,
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
  applyReviewSkillUpdates(input: ReviewSkillUpdateInput): Promise<void>
  /** Commit 63: technique EMA + rolling history (post-Review). */
  applySessionMutation(updates: SkillSessionMutationRow[]): Promise<void>
  insertJamSnapshotRow(input: JamSnapshotInsertInput): Promise<void>
  listJamSnapshots(): Promise<JamSnapshotRow[]>
  insertPracticePlanCompletionRow(input: PracticePlanCompletionInsertInput): Promise<void>
  listPracticePlanCompletions(): Promise<PracticePlanCompletionRow[]>
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
}
