import type {
  HomeSuggestion,
  JamSnapshotInsertInput,
  JamSnapshotRow,
  LickInsertInput,
  LickRow,
  LatestSessionSongRow,
  LessonListRow,
  NodeSessionSnippet,
  ReviewSkillUpdateInput,
  SessionArchiveRow,
  SessionInsertInput,
  SessionJournalRow,
  SkillNodeRow,
} from '@/src/db/types'
import type { LessonJSON } from '@/src/types'

/**
 * Shared repository surface for `client.native` (SQLite) and `client.web` (IndexedDB + memory).
 * Metro picks the platform implementation; this type keeps APIs aligned (PRIORITIES §38).
 */
export interface HarmoniqDbClient {
  initDb(): Promise<void>
  insertSessionRow(input: SessionInsertInput): Promise<void>
  getSessionCount(): Promise<number>
  listSessionsJournal(): Promise<SessionJournalRow[]>
  getSessionById(id: string): Promise<SessionArchiveRow | null>
  getLatestSessionSnippetForNode(nodeId: string): Promise<NodeSessionSnippet | null>
  getAllSkillNodes(): Promise<SkillNodeRow[]>
  getAppPref(key: string): Promise<string | null>
  setAppPref(key: string, value: string): Promise<void>
  getOnboardingComplete(): Promise<boolean>
  setOnboardingComplete(): Promise<void>
  commitPlacementOnboarding(aggregatedNodeScores: Record<string, number>): Promise<void>
  getLatestSessionWithSong(): Promise<LatestSessionSongRow | null>
  getHomeSuggestion(): Promise<HomeSuggestion>
  applyReviewSkillUpdates(input: ReviewSkillUpdateInput): Promise<void>
  insertJamSnapshotRow(input: JamSnapshotInsertInput): Promise<void>
  listJamSnapshots(): Promise<JamSnapshotRow[]>
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
