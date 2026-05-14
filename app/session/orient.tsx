/**
 * Orient phase screen for commit #84.
 *
 * Shows the stem mixer (three cards) plus an animated fretboard visualisation
 * synced to playback, replacing the old orient clip audio button.
 */

import { useRouter } from 'expo-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Text, View } from 'react-native'

import { ListenStemPanel, type ListenStemPanelHandle } from '@/components/ListenStemPanel'
import { OrientFretboardPlayer } from '@/components/OrientFretboardPlayer'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import { sessionHref } from '@/src/constants/sessionFlow'
import { useLessonStore } from '@/src/stores/lessonStore'

export default function OrientScreen() {
  const router = useRouter()
  const lesson = useLessonStore((s) => s.lesson)
  const stemTabRef = useRef<ListenStemPanelHandle>(null)

  const [annotation, setAnnotation] = useState<string | null>(null)
  const [orientError, setOrientError] = useState<string | null>(null)
  const [positionSec, setPositionSec] = useState(0)

  // Fetch orient clip annotation from backend.
  useEffect(() => {
    const fetchAnnotation = async () => {
      if (!lesson?.job_id) return
      setOrientError(null)
      try {
        const response = await fetch(`${process.env.EXPO_PUBLIC_API_URL}/session/orient-clip`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            job_id: lesson.job_id,
            style_label: lesson.style_label,
            technique: null,
            key: lesson.key,
            bpm: lesson.tempo,
          }),
        })
        if (!response.ok) throw new Error(`Failed to fetch orient clip: ${response.statusText}`)
        const data = await response.json()
        setAnnotation(data.annotation)
      } catch (e) {
        console.error('Failed to fetch orient clip:', e)
        setOrientError(e instanceof Error ? e.message : 'Failed to load orient clip')
      }
    }
    void fetchAnnotation()
  }, [lesson?.job_id, lesson?.style_label, lesson?.key, lesson?.tempo])

  const handlePlaybackTick = useCallback(
    (ctx: { positionSec: number; playing: boolean }) => {
      setPositionSec(ctx.positionSec)
    },
    [],
  )

  const handleSeek = useCallback(
    (sec: number) => {
      void stemTabRef.current?.seekTransportToSeconds(sec)
    },
    [],
  )

  return (
    <SessionStepScreen
      title="Orient"
      subtitle="Listen to how the piece is played — use the mixer, then watch the fretboard"
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Study"
      onNext={() => router.push(sessionHref('study'))}
    >
      <View className="gap-4">
        {orientError ? (
          <Text className="font-sans text-sm text-danger">{orientError}</Text>
        ) : null}

        <ListenStemPanel
          ref={stemTabRef}
          autoPlayOnReady={lesson?.job_id === DEMO_LESSON_JOB_ID}
          onPlaybackTick={handlePlaybackTick}
        />

        {lesson ? (
          <OrientFretboardPlayer
            lesson={lesson}
            positionSec={positionSec}
            orientAnnotation={annotation}
            onSeek={handleSeek}
          />
        ) : null}
      </View>
    </SessionStepScreen>
  )
}
