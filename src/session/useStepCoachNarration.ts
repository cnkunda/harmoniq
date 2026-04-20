import { useFocusEffect } from '@react-navigation/native'
import { useCallback, useRef } from 'react'

import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import { speak } from '@/src/audio/voiceCoach'
import { useLessonStore } from '@/src/stores/lessonStore'
import { useVoiceCoachPrefsStore } from '@/src/stores/voiceCoachPrefsStore'

/**
 * On step focus, read the current section `coach_note` when voice coach is enabled
 * and `disableWhile()` is false (commit 72).
 */
export function useStepCoachNarration(disableWhile?: () => boolean): void {
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const disableRef = useRef(disableWhile)
  disableRef.current = disableWhile

  useFocusEffect(
    useCallback(() => {
      if (disableRef.current?.()) return
      if (!useVoiceCoachPrefsStore.getState().enabled) return
      if (lesson?.job_id === DEMO_LESSON_JOB_ID) return
      const sec = lesson?.sections?.[lessonSectionIndex] as Record<string, unknown> | undefined
      const note = typeof sec?.coach_note === 'string' ? sec.coach_note.trim() : ''
      if (!note) return
      speak(note)
    }, [lesson?.job_id, lessonSectionIndex, lesson?.sections]),
  )
}
