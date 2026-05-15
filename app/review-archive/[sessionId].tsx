import { useLocalSearchParams, useRouter } from 'expo-router'
import { useEffect, useState } from 'react'
import { ScrollView, Text, View } from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { PhrasingVisualizerStub, ScoreSummaryCard } from '@/components/ReviewSessionPanel'
import { WaveformPlaybackActions } from '@/components/WaveformPlaybackActions'
import { getSessionById } from '@/src/db/client'
import type { SessionArchiveRow } from '@/src/db/types'
import { parseScoreSnapshot } from '@/src/utils/parseScoreSnapshot'

export default function ReviewArchiveScreen() {
  const router = useRouter()
  const params = useLocalSearchParams<{ sessionId: string | string[] }>()
  const sessionId = Array.isArray(params.sessionId) ? params.sessionId[0] : params.sessionId
  const [row, setRow] = useState<SessionArchiveRow | null | undefined>(undefined)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (typeof sessionId !== 'string' || sessionId.length === 0) {
      setRow(null)
      setErr('Missing session id.')
      return
    }
    let cancelled = false
    void getSessionById(sessionId)
      .then((r) => {
        if (!cancelled) {
          setRow(r ?? null)
          setErr(r ? null : 'Session not found.')
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setRow(null)
          setErr(e instanceof Error ? e.message : 'Could not load session.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  const score = row?.review_snapshot ? parseScoreSnapshot(row.review_snapshot) : null
  const hasWave =
    (score?.waveform_comparison.user_wav_base64?.length ?? 0) > 0 ||
    (score?.waveform_comparison.reference_wav_base64?.length ?? 0) > 0 ||
    (row?.waveform_user_path?.length ?? 0) > 0 ||
    (row?.waveform_ref_path?.length ?? 0) > 0

  return (
    <SafeAreaView className="flex-1 bg-ivory" edges={['top', 'left', 'right']}>
      <ScrollView className="flex-1 px-5 py-4" contentContainerStyle={{ paddingBottom: 32 }}>
        <Text className="font-serif text-2xl text-wood-900">Session replay</Text>
        <Text className="mt-1 font-sans text-sm text-muted-brown">Read-only review from your journal.</Text>

        <AnimatedPressable haptic="light"
          onPress={() => router.back()}
          className="mt-4 self-start rounded-lg border border-wood-600/45 bg-cream-dark/45 px-3 py-2"
          accessibilityRole="button"
          accessibilityLabel="Go back"
        >
          <Text className="font-sans-medium text-sm text-wood-900">Back</Text>
        </AnimatedPressable>

        {row === undefined ? (
          <Text className="mt-6 font-sans text-sm text-muted-brown">Loading…</Text>
        ) : err && !row ? (
          <View className="mt-6 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2">
            <Text className="font-sans text-sm text-danger">{err}</Text>
          </View>
        ) : row ? (
          <>
            <View className="mt-6 rounded-xl border border-wood-600/45 bg-cream-dark/40 px-3 py-3">
              <Text className="font-sans-medium text-sm text-wood-900">
                {[row.song_title, row.artist].filter(Boolean).join(' · ') || 'Practice session'}
              </Text>
              {row.section_label ? (
                <Text className="mt-1 font-sans text-xs text-muted-brown">Section: {row.section_label}</Text>
              ) : null}
              <Text className="mt-1 font-mono text-[11px] text-muted-brown">{row.date}</Text>
              {row.coach_review ? (
                <Text className="mt-3 font-sans text-sm leading-6 text-wood-900">{row.coach_review}</Text>
              ) : null}
            </View>

            <PhrasingVisualizerStub />

            {hasWave && score ? (
              <WaveformPlaybackActions
                userWavBase64={score.waveform_comparison.user_wav_base64}
                referenceWavBase64={score.waveform_comparison.reference_wav_base64}
                userFileUri={row.waveform_user_path}
                referenceFileUri={row.waveform_ref_path}
              />
            ) : null}

            {score ? (
              <ScoreSummaryCard score={score} />
            ) : (
              <View className="mt-4 rounded-lg border border-wood-600/40 bg-wood-800/10 px-3 py-3">
                <Text className="font-sans text-sm text-muted-brown">
                  No score snapshot for this session. Newer sessions save full review data automatically after you run
                  score.
                </Text>
              </View>
            )}
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  )
}
