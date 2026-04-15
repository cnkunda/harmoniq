import { useLocalSearchParams, useRouter } from 'expo-router'
import { useEffect, useRef } from 'react'

import { SessionStemAndTab, type SessionStemAndTabHandle } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'
import { useLessonStore } from '@/src/stores/lessonStore'
import { sectionSeekSeconds } from '@/src/utils/lessonAudio'

export default function ListenScreen() {
  const router = useRouter()
  const params = useLocalSearchParams<{ section?: string }>()
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const lessonJobId = useLessonStore((s) => s.lesson?.job_id ?? '')
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const stemTabRef = useRef<SessionStemAndTabHandle>(null)

  useEffect(() => {
    const raw = params.section
    if (raw == null) return
    const s = Array.isArray(raw) ? raw[0] : raw
    const n = parseInt(s, 10)
    if (!Number.isNaN(n) && n >= 0) setLessonSectionIndex(n)
  }, [params.section, setLessonSectionIndex])

  /** Keep stems + tab cursor aligned with the active section (URL param, chips, or initial index). */
  useEffect(() => {
    const l = useLessonStore.getState().lesson
    if (!l) return
    const idx = useLessonStore.getState().lessonSectionIndex
    const t = sectionSeekSeconds(l, idx)
    void stemTabRef.current?.seekTransportToSeconds(t)
  }, [lessonJobId, lessonSectionIndex])

  const exitSession = () => {
    if (router.canGoBack()) router.back()
    else router.replace('/(tabs)')
  }

  return (
    <SessionStepScreen
      title="Listen"
      subtitle="Familiarize yourself with the piece before playing"
      showBack
      backLabel="Close"
      onBack={exitSession}
      showNext
      nextLabel="Next: Study"
      onNext={() => router.push(sessionHref('study'))}
    >
      <SessionStemAndTab ref={stemTabRef} />
    </SessionStepScreen>
  )
}
