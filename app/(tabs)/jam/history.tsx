import { useRouter } from 'expo-router'
import { useCallback, useEffect, useState } from 'react'
import { ActivityIndicator, ScrollView, Text, View } from 'react-native'
import { ArrowLeft } from 'lucide-react-native'
import { SafeAreaView } from 'react-native-safe-area-context'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { JamSummaryModal, type JamSummaryStatus } from '@/components/JamSummaryModal'
import { toast } from '@/components/ToastConfig'
import { WoodGradient } from '@/components/WoodGradient'
import type { JamPhraseMetrics, JamSummaryBundle } from '@/src/api/jam'
import { colors } from '@/src/constants/colors'
import type { BackingTrackDefinition } from '@/src/constants/backingTracks'
import { initDb, listJamSnapshots } from '@/src/db/client'
import type { JamSnapshotRow } from '@/src/db/types'
import { buildJamPracticeHref, resolveJamPracticeTrack } from '@/src/jam/jamPracticeTrack'
import { parseStoredPhrases, retryJamSummary } from '@/src/jam/jamSummaryRunner'

type SelectedSummary = {
  row: JamSnapshotRow
  status: JamSummaryStatus
  bundle: JamSummaryBundle | null
  coachSummary: string
  phrases: JamPhraseMetrics[]
  track: BackingTrackDefinition | null
}

function parseBundle(raw: string | null): JamSummaryBundle | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as JamSummaryBundle
  } catch (e) {
    console.warn('[JamHistory] could not parse summary bundle', e)
    return null
  }
}

function rowStatus(row: JamSnapshotRow): JamSummaryStatus {
  if (
    row.summary_status === 'pending' ||
    row.summary_status === 'ready' ||
    row.summary_status === 'failed' ||
    row.summary_status === 'skipped'
  ) {
    return row.summary_status
  }
  return 'ready'
}

function statusLabel(status: JamSummaryStatus): string {
  if (status === 'ready') return 'Summary ready'
  if (status === 'pending') return 'Analyzing…'
  if (status === 'failed') return 'Summary failed'
  return 'No phrase summary'
}

function formatDate(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function buildSelected(row: JamSnapshotRow): SelectedSummary {
  const bundle = parseBundle(row.summary_bundle_json)
  return {
    row,
    status: rowStatus(row),
    bundle,
    coachSummary: bundle?.coach_summary || row.coach_summary,
    phrases: parseStoredPhrases(row.phrases_json),
    track: resolveJamPracticeTrack({
      trackId: row.track_id,
      trackKey: row.track_key,
      trackBpm: row.track_bpm,
    }),
  }
}

export default function JamHistoryScreen() {
  const router = useRouter()
  const [rows, setRows] = useState<JamSnapshotRow[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<SelectedSummary | null>(null)
  const [retrying, setRetrying] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        await initDb()
        const snapshots = await listJamSnapshots()
        if (!cancelled) setRows(snapshots)
      } catch (e) {
        console.error('[JamHistory] could not load jam snapshots', e)
        toast.error('Could not load jam history.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const handleRetry = useCallback(async () => {
    if (!selected || retrying) return
    const row = selected.row
    setRetrying(true)
    setSelected((prev) => (prev ? { ...prev, status: 'pending' } : prev))
    try {
      const bundle = await retryJamSummary(row)
      setSelected((prev) =>
        prev
          ? {
              ...prev,
              status: 'ready',
              bundle,
              coachSummary: bundle.coach_summary || prev.coachSummary,
            }
          : prev,
      )
      setRows((prev) =>
        prev.map((item) =>
          item.id === row.id
            ? {
                ...item,
                summary_bundle_json: JSON.stringify(bundle),
                coach_summary: bundle.coach_summary || item.coach_summary,
                summary_status: 'ready',
              }
            : item,
        ),
      )
      toast.success('Jam summary ready.')
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Could not regenerate the summary'
      setSelected((prev) => (prev ? { ...prev, status: 'failed' } : prev))
      setRows((prev) =>
        prev.map((item) =>
          item.id === row.id ? { ...item, summary_status: 'failed', summary_bundle_json: null } : item,
        ),
      )
      toast.error(message)
    } finally {
      setRetrying(false)
    }
  }, [retrying, selected])

  const practicePhrase = useCallback(
    (phraseIndex: number, startMs: number | null | undefined, endMs: number | null | undefined) => {
      const track = selected?.track
      if (!track || startMs == null || endMs == null || endMs <= startMs) {
        toast.error('This phrase has no matching backing loop.')
        return
      }
      setSelected(null)
      router.push(
        buildJamPracticeHref({
          trackId: track.id,
          startMs,
          endMs,
          phraseIndex,
        }),
      )
    },
    [router, selected?.track],
  )

  return (
    <WoodGradient className="flex-1">
      <SafeAreaView className="flex-1" edges={['top', 'left', 'right']}>
        <View className="mt-3 flex-row items-center justify-between px-5">
          <View className="flex-row items-center gap-3">
            <AnimatedPressable
              onPress={() => router.back()}
              haptic="light"
              className="min-h-[44px] min-w-[44px] items-center justify-center"
              accessibilityRole="button"
              accessibilityLabel="Back to Jam"
            >
              <ArrowLeft color={colors.cream} size={22} />
            </AnimatedPressable>
            <Text className="font-serif text-3xl text-cream">Jam history</Text>
          </View>
        </View>

        {loading ? (
          <View className="flex-1 items-center justify-center">
            <ActivityIndicator color={colors.amber.light} />
          </View>
        ) : rows.length === 0 ? (
          <View className="mx-5 mt-8 rounded-2xl border border-wood-700/60 bg-wood-800/50 p-5">
            <Text className="font-serif text-xl text-cream">No jams yet</Text>
            <Text className="mt-2 font-sans text-sm leading-relaxed text-cream/75">
              Record a jam from Jam Mode, then come back to revisit the coaching and practice individual phrases.
            </Text>
          </View>
        ) : (
          <ScrollView className="flex-1 px-5" contentContainerStyle={{ paddingTop: 16, paddingBottom: 24 }}>
            <View className="gap-3">
              {rows.map((row) => {
                const bundle = parseBundle(row.summary_bundle_json)
                const status = rowStatus(row)
                const track = resolveJamPracticeTrack({
                  trackId: row.track_id,
                  trackKey: row.track_key,
                  trackBpm: row.track_bpm,
                })
                return (
                  <AnimatedPressable
                    key={row.id}
                    onPress={() => setSelected(buildSelected(row))}
                    haptic="light"
                    className="rounded-2xl border border-wood-700/60 bg-wood-800/50 p-4"
                    accessibilityRole="button"
                    accessibilityLabel={`Open jam from ${formatDate(row.date)}`}
                  >
                    <View className="flex-row items-start justify-between gap-3">
                      <View className="flex-1">
                        <Text className="font-sans-medium text-sm text-cream">
                          {row.track_label || 'Jam session'}
                        </Text>
                        <Text className="mt-1 font-sans text-xs text-muted-light">
                          {formatDate(row.date)} · {row.duration_seconds}s
                          {row.track_key ? ` · ${row.track_key}` : ''}
                        </Text>
                        <Text className="mt-1 font-sans text-xs text-muted-brown">
                          {track ? `Loop: ${track.label}` : 'No matching classic loop'}
                        </Text>
                      </View>
                      <View className="items-end gap-1">
                        {bundle ? (
                          <Text
                            className="font-serif-bold text-2xl"
                            style={{
                              color:
                                bundle.grade === 'A' || bundle.grade === 'B'
                                  ? colors.success
                                  : bundle.grade === 'C'
                                    ? colors.amber.accent
                                    : colors.danger,
                            }}
                          >
                            {bundle.grade}
                          </Text>
                        ) : null}
                        <Text
                          className={`font-sans text-[11px] ${
                            status === 'failed' ? 'text-danger' : 'text-muted-light'
                          }`}
                        >
                          {statusLabel(status)}
                        </Text>
                      </View>
                    </View>
                  </AnimatedPressable>
                )
              })}
            </View>
          </ScrollView>
        )}
      </SafeAreaView>

      <JamSummaryModal
        visible={selected != null}
        status={selected?.status ?? 'skipped'}
        bundle={selected?.bundle ?? null}
        coachSummary={selected?.coachSummary ?? ''}
        phrases={selected?.phrases ?? []}
        track={selected?.track ?? null}
        onClose={() => {
          if (!retrying) setSelected(null)
        }}
        onRetry={selected?.status === 'failed' && !retrying ? () => void handleRetry() : undefined}
        onPracticePhrase={(feedback, metrics) =>
          practicePhrase(feedback.phrase_index, metrics.backing_start_ms, metrics.backing_end_ms)
        }
      />
    </WoodGradient>
  )
}
