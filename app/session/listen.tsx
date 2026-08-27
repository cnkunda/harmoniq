import { Audio } from 'expo-av'
import { useLocalSearchParams, useRouter } from 'expo-router'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Modal, ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { DemoTourCallout } from '@/components/DemoTourCallout'
import { ListenStemPanel, type ListenStemPanelHandle } from '@/components/ListenStemPanel'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'
import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import { DEMO_TOUR_CALLOUT, DEMO_TOUR_SUBTITLE } from '@/src/demo/demoSessionTourCopy'
import { useIsDemoLesson } from '@/src/demo/useIsDemoLesson'
import { useStepCoachNarration } from '@/src/session/useStepCoachNarration'
import { useLessonStore } from '@/src/stores/lessonStore'
import { sectionSeekSeconds } from '@/src/utils/lessonAudio'
import colors from '@/src/constants/colors'
import { Film, Pause, Play, X } from 'lucide-react-native'

export default function ListenScreen() {
  useStepCoachNarration()
  const isDemo = useIsDemoLesson()
  const router = useRouter()
  const params = useLocalSearchParams<{ section?: string }>()
  const setLessonSectionIndex = useLessonStore((s) => s.setLessonSectionIndex)
  const lesson = useLessonStore((s) => s.lesson)
  const lessonJobId = lesson?.job_id ?? ''
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const stemTabRef = useRef<ListenStemPanelHandle>(null)

  const [orientClipUrl, setOrientClipUrl] = useState<string | null>(null)
  const [orientAnnotation, setOrientAnnotation] = useState<string | null>(null)
  const [orientIsPlaying, setOrientIsPlaying] = useState(false)
  const [orientModalVisible, setOrientModalVisible] = useState(false)
  const [orientIsLoading, setOrientIsLoading] = useState(false)
  const [orientError, setOrientError] = useState<string | null>(null)
  const orientSoundRef = useRef<Audio.Sound | null>(null)

  useEffect(() => {
    const raw = params.section
    if (raw == null) return
    const s = Array.isArray(raw) ? raw[0] : raw
    const n = parseInt(s, 10)
    if (!Number.isNaN(n) && n >= 0) setLessonSectionIndex(n)
  }, [params.section, setLessonSectionIndex])

  useEffect(() => {
    const l = useLessonStore.getState().lesson
    if (!l) return
    const idx = useLessonStore.getState().lessonSectionIndex
    const t = sectionSeekSeconds(l, idx)
    void stemTabRef.current?.seekTransportToSeconds(t)
  }, [lessonJobId, lessonSectionIndex])

  // Fetch orient clip
  useEffect(() => {
    const fetchOrientClip = async () => {
      if (!lesson?.job_id) return
      setOrientIsLoading(true)
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
        setOrientClipUrl(data.wav_path)
        setOrientAnnotation(data.annotation)
      } catch (e) {
        console.error('Failed to fetch orient clip:', e)
        setOrientError(e instanceof Error ? e.message : 'Failed to load orient clip')
      } finally {
        setOrientIsLoading(false)
      }
    }
    void fetchOrientClip()
  }, [lesson?.job_id, lesson?.style_label, lesson?.key, lesson?.tempo])

  // Cleanup orient sound on unmount
  useEffect(() => {
    return () => {
      if (orientSoundRef.current) {
        orientSoundRef.current.unloadAsync()
      }
    }
  }, [])

  const handleToggleOrientPlayback = useCallback(async () => {
    if (!orientClipUrl) return
    try {
      if (orientIsPlaying) {
        const sound = orientSoundRef.current
        if (sound) {
          await sound.pauseAsync()
          setOrientIsPlaying(false)
        }
      } else {
        if (orientSoundRef.current) {
          await orientSoundRef.current.playAsync()
          setOrientIsPlaying(true)
        } else {
          const { sound } = await Audio.Sound.createAsync(
            { uri: orientClipUrl },
            { shouldPlay: true },
          )
          orientSoundRef.current = sound
          setOrientIsPlaying(true)
          sound.setOnPlaybackStatusUpdate((status) => {
            if (status.isLoaded && status.didJustFinish) {
              setOrientIsPlaying(false)
            }
          })
        }
      }
    } catch (e) {
      console.error('Orient playback error:', e)
      setOrientError('Could not play orient clip')
    }
  }, [orientClipUrl, orientIsPlaying])

  const openOrientModal = useCallback(() => {
    setOrientModalVisible(true)
  }, [])

  const closeOrientModal = useCallback(() => {
    setOrientModalVisible(false)
    if (orientSoundRef.current) {
      orientSoundRef.current.stopAsync().catch(() => {})
      orientSoundRef.current.unloadAsync().catch(() => {})
      orientSoundRef.current = null
    }
    setOrientIsPlaying(false)
  }, [])

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

      <ListenStemPanel
        ref={stemTabRef}
        autoPlayOnReady={lesson?.job_id === DEMO_LESSON_JOB_ID}
      />

      <View className="mt-6">
        <AnimatedPressable haptic="light"
          onPress={openOrientModal}
          disabled={orientIsLoading}
          className="min-h-[80px] items-center justify-center gap-3 rounded-xl border border-wood-700/50 bg-wood-800/35 py-4 active:bg-wood-700/50 disabled:opacity-50"
          accessibilityRole="button"
          accessibilityLabel={
            orientIsLoading
              ? 'Loading performance guide'
              : orientError
                ? 'Performance guide unavailable'
                : 'Watch how this song is played'
          }
        >
          <View className="h-10 w-10 items-center justify-center rounded-full bg-wood-700">
            <Film color={colors.amber.light} size={20} strokeWidth={2} />
          </View>
          <Text className="text-center font-sans-medium text-sm text-cream">
            {orientIsLoading ? 'Loading…' : orientError ? 'Unavailable' : 'Watch How It\'s Played'}
          </Text>
        </AnimatedPressable>
      </View>

      <Modal
        visible={orientModalVisible}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={closeOrientModal}
      >
        <SafeAreaView className="flex-1 bg-wood-900">
          <View className="flex-row justify-end px-4 pt-2">
            <AnimatedPressable haptic="light"
              onPress={closeOrientModal}
              className="h-10 w-10 items-center justify-center rounded-full bg-wood-800 active:bg-wood-700"
              accessibilityRole="button"
              accessibilityLabel="Close performance guide"
            >
              <X color={colors.amber.light} size={20} strokeWidth={2} />
            </AnimatedPressable>
          </View>

          <ScrollView className="flex-1" showsVerticalScrollIndicator={false}>
            <View className="mx-4 mt-2">
              <View className="h-64 items-center justify-center rounded-xl border border-wood-600/50 bg-wood-800">
                {orientClipUrl ? (
                  <AnimatedPressable haptic="light"
                    onPress={handleToggleOrientPlayback}
                    className="h-full w-full items-center justify-center"
                    accessibilityRole="button"
                    accessibilityLabel={orientIsPlaying ? 'Pause performance' : 'Play performance'}
                  >
                    {orientIsPlaying ? (
                      <Pause color={colors.amber.accent} size={52} strokeWidth={1.5} />
                    ) : (
                      <Play color={colors.amber.accent} size={52} strokeWidth={1.5} />
                    )}
                  </AnimatedPressable>
                ) : (
                  <View className="items-center gap-3 px-6">
                    <Film color={colors.muted.light} size={40} strokeWidth={1.5} />
                    <Text className="text-center font-sans text-sm text-muted-light">
                      {orientIsLoading
                        ? 'Loading performance guide…'
                        : orientError
                          ? 'Performance guide not available for this song.'
                          : 'AI-generated video demonstration coming soon'}
                    </Text>
                  </View>
                )}
              </View>

              <Text className="mt-6 font-serif text-2xl text-cream">Performance Guide</Text>
              <Text className="mt-1 font-sans text-sm text-muted-light">
                Watch and listen to how this section is played.
              </Text>

              {orientAnnotation ? (
                <View className="mt-4 rounded-xl border border-wood-600/50 bg-wood-800/40 p-4">
                  <Text className="font-sans text-sm leading-relaxed text-cream/80">
                    {orientAnnotation}
                  </Text>
                </View>
              ) : null}

              {orientError && !orientClipUrl ? (
                <View className="mt-4 rounded-xl border border-danger/30 bg-danger/10 p-4">
                  <Text className="font-sans text-sm text-danger">{orientError}</Text>
                </View>
              ) : null}
            </View>
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </SessionStepScreen>
  )
}
