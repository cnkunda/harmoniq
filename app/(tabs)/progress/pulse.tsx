import { useFocusEffect } from '@react-navigation/native'
import { useRouter } from 'expo-router'
import { ChevronLeft } from 'lucide-react-native'
import { useCallback, useMemo, useState } from 'react'
import { ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AccuracyTrendChart } from '@/components/pulse/AccuracyTrendChart'
import { ChordMasteryHeatmap } from '@/components/pulse/ChordMasteryHeatmap'
import { PulseStage } from '@/components/pulse/PulseStage'
import { AnimatedPressable } from '@/components/AnimatedPressable'
import { toast } from '@/components/ToastConfig'
import { WoodGradient } from '@/components/WoodGradient'
import { colors } from '@/src/constants/colors'
import {
  getLessonByJobId,
  listLessonsJournal,
  listSessionsJournal,
  listUserFeedback,
} from '@/src/db/client'
import type { SessionJournalRow, UserFeedbackRow } from '@/src/db/types'
import { getDemoLesson } from '@/src/demo/demoLesson'
import {
  buildAccuracyTrend,
  buildChordMastery,
  buildPulseStageData,
  type SessionLessonPair,
} from '@/src/progress/pulseData'
import type { LessonJSON } from '@/src/types'

export default function PulseScreen() {
  const router = useRouter()
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [sessions, setSessions] = useState<SessionJournalRow[]>([])
  const [feedback, setFeedback] = useState<UserFeedbackRow[]>([])
  const [latestLesson, setLatestLesson] = useState<LessonJSON | null>(null)
  const [sessionLessons, setSessionLessons] = useState<SessionLessonPair[]>([])
  const [previewDemo, setPreviewDemo] = useState(false)

  const refresh = useCallback(() => {
    let cancelled = false
    setLoading(true)
    setLoadError(null)

    void (async () => {
      try {
        const [sessionRows, lessonRows, feedbackRows] = await Promise.all([
          listSessionsJournal(),
          listLessonsJournal(),
          listUserFeedback(),
        ])

        const firstSessionByJob = new Map<string, SessionJournalRow>()
        for (const session of sessionRows) {
          if (session.job_id && !firstSessionByJob.has(session.job_id)) {
            firstSessionByJob.set(session.job_id, session)
          }
        }
        const jobIds = [...firstSessionByJob.keys()].slice(0, 10)
        const selectedJobId = jobIds[0] ?? lessonRows[0]?.job_id ?? null
        const neededJobIds = [...new Set([selectedJobId, ...jobIds].filter((id): id is string => Boolean(id)))]

        const loadedLessons = await Promise.all(neededJobIds.map((jobId) => getLessonByJobId(jobId)))
        const lessonByJob = new Map<string, LessonJSON | null>()
        neededJobIds.forEach((jobId, index) => {
          lessonByJob.set(jobId, loadedLessons[index] ?? null)
        })

        const pairs: SessionLessonPair[] = jobIds.map((jobId) => ({
          session: firstSessionByJob.get(jobId)!,
          lesson: lessonByJob.get(jobId) ?? null,
        }))

        if (cancelled) return
        setSessions(sessionRows)
        setFeedback(feedbackRows)
        setSessionLessons(pairs)
        setLatestLesson(selectedJobId ? (lessonByJob.get(selectedJobId) ?? null) : null)
        if (selectedJobId && lessonByJob.get(selectedJobId)) setPreviewDemo(false)
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown error'
        console.error('[Pulse] could not load pulse data', error)
        toast.error(`Could not load Chord Pulse: ${message}`)
        if (!cancelled) setLoadError(message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  useFocusEffect(
    useCallback(() => refresh(), [refresh]),
  )

  const demoLesson = useMemo(() => getDemoLesson(), [])
  const stageLesson = latestLesson ?? (previewDemo ? demoLesson : null)
  const stage = useMemo(() => buildPulseStageData(stageLesson), [stageLesson])
  const trend = useMemo(() => buildAccuracyTrend(sessions, 10), [sessions])
  const heatmap = useMemo(() => buildChordMastery(sessionLessons, feedback), [sessionLessons, feedback])
  const trackTitle = stageLesson?.song_title?.trim() || stageLesson?.artist?.trim() || null

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1" edges={['top', 'left', 'right']}>
        <ScrollView
          className="flex-1"
          contentContainerStyle={{ paddingBottom: 40 }}
          showsVerticalScrollIndicator={false}
        >
          <View className="w-full max-w-4xl self-center px-6 pb-8 pt-4">
            <View className="mb-7 mt-2 flex-row items-center gap-3">
              <AnimatedPressable
                onPress={() => router.back()}
                haptic="light"
                accessibilityRole="button"
                accessibilityLabel="Back to progress"
                className="flex h-11 w-11 items-center justify-center rounded-full border border-wood-600/50 bg-wood-800/60"
              >
                <ChevronLeft color={colors.cream} size={20} strokeWidth={2} />
              </AnimatedPressable>
              <View className="flex-1">
                <Text className="font-serif text-3xl text-cream">Chord Pulse</Text>
                <Text className="mt-0.5 font-sans text-sm text-muted-light">
                  A beat-synced look at the chords you have practiced.
                </Text>
              </View>
            </View>

            {loading ? (
              <View className="rounded-2xl border border-wood-600/45 bg-wood-800/40 px-6 py-10">
                <Text className="font-serif text-xl text-cream">Tuning the pulse…</Text>
                <Text className="mt-2 font-sans text-sm text-muted-light">
                  Reading your sessions, chords, and corrections.
                </Text>
              </View>
            ) : loadError ? (
              <View className="rounded-2xl border border-danger/40 bg-danger/10 px-6 py-6">
                <Text className="font-serif text-xl text-cream">Chord Pulse could not load</Text>
                <Text className="mt-2 font-sans text-sm leading-6 text-muted-light">{loadError}</Text>
                <AnimatedPressable
                  onPress={refresh}
                  haptic="light"
                  accessibilityRole="button"
                  accessibilityLabel="Retry loading Chord Pulse"
                  className="mt-4 self-start rounded-full border border-amber-accent/50 bg-amber-accent/15 px-4 py-2"
                >
                  <Text className="font-sans-medium text-sm text-amber-light">Try again</Text>
                </AnimatedPressable>
              </View>
            ) : (
              <>
                <View className="mb-8">
                  <PulseStage
                    stage={stage}
                    trackTitle={trackTitle}
                    isDemoPreview={previewDemo && !latestLesson}
                    onPreviewDemo={latestLesson ? undefined : () => setPreviewDemo(true)}
                  />
                </View>

                <View className="mb-8 rounded-2xl border border-wood-600/45 bg-wood-800/40 p-5">
                  <AccuracyTrendChart points={trend} />
                </View>

                <View className="rounded-2xl border border-wood-600/45 bg-wood-800/40 p-5">
                  <ChordMasteryHeatmap heatmap={heatmap} />
                </View>
              </>
            )}
          </View>
        </ScrollView>
      </SafeAreaView>
    </WoodGradient>
  )
}
