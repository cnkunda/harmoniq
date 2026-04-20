import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import { useLessonStore } from '@/src/stores/lessonStore'

/** True when the active workspace lesson is the bundled offline demo (`getDemoLesson`). */
export function useIsDemoLesson(): boolean {
  const jobId = useLessonStore((s) => s.lesson?.job_id)
  return jobId === DEMO_LESSON_JOB_ID
}
