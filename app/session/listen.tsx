import { useLocalSearchParams, useRouter } from 'expo-router'
import { useEffect, useRef, useState } from 'react'

import { DemoTourCallout } from '@/components/DemoTourCallout'
import { SessionStemAndTab, type SessionStemAndTabHandle } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { SongDetailsCard } from '@/components/SongDetailsCard'
import { sessionHref } from '@/src/constants/sessionFlow'
import { useStepCoachNarration } from '@/src/session/useStepCoachNarration'
import { useLessonStore } from '@/src/stores/lessonStore'
import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import { sectionSeekSeconds } from '@/src/utils/lessonAudio'
import type { SongScoreMeta } from '@/types/tabMessage'

export default function ListenScreen() {
  useStepCoachNarration()
  const isDemo = useIsDemoLesson()
  const router = useRouter()
  const params = useLocalSearchParams<{ section?: string }>()
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const lesson = useLessonStore((s) => s.lesson)
  const lessonJobId = lesson?.job_id ?? ''
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const stemTabRef = useRef<SessionStemAndTabHandle>(null)
  const [scoreMeta, setScoreMeta] = useState<SongScoreMeta | null>(null)
  const [songPlayback, setSongPlayback] = useState<{
    masterBarIndex: number
    sectionLabel: string | null
  } | null>(null)

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
      subtitle={
        isDemo ? DEMO_TOUR_SUBTITLE.listen : 'Familiarize yourself with the piece before playing'
      }
      showBack
      backLabel="Close"
      onBack={exitSession}
      showNext
      nextLabel="Next: Study"
      onNext={() => router.push(sessionHref('study'))}
    >
      {isDemo ? <DemoTourCallout>{DEMO_TOUR_CALLOUT.listen}</DemoTourCallout> : null}
      <SessionStemAndTab
        ref={stemTabRef}
        tabRenderPreset="listen"
        autoPlayOnReady={lesson?.job_id === DEMO_LESSON_JOB_ID}
        onTabSongDetails={setScoreMeta}
        onTabSongPlayback={setSongPlayback}
        detailsAboveTab={
          <SongDetailsCard
            lesson={lesson}
            scoreMeta={scoreMeta}
            playback={songPlayback}
            lessonSectionIndex={lessonSectionIndex}
          />
        }
      />
    </SessionStepScreen>
  )
}
