import { useLocalSearchParams, useRouter } from 'expo-router'
import { useEffect } from 'react'

import { SessionStemAndTab } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'
import { useLessonStore } from '@/src/stores/lessonStore'

export default function ListenScreen() {
  const router = useRouter()
  const params = useLocalSearchParams<{ section?: string }>()
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)

  useEffect(() => {
    const raw = params.section
    if (raw == null) return
    const s = Array.isArray(raw) ? raw[0] : raw
    const n = parseInt(s, 10)
    if (!Number.isNaN(n) && n >= 0) setLessonSectionIndex(n)
  }, [params.section, setLessonSectionIndex])

  const exitSession = () => {
    if (router.canGoBack()) router.back()
    else router.replace('/(tabs)')
  }

  return (
    <SessionStepScreen
      title="Listen"
      subtitle="Stems + tab with AlphaTab external-media sync (audio timeline drives cursor)."
      showBack
      backLabel="Close"
      onBack={exitSession}
      showNext
      nextLabel="Next: Study"
      onNext={() => router.push(sessionHref('study'))}
    >
      <SessionStemAndTab />
    </SessionStepScreen>
  )
}
