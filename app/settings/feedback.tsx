import { useRouter } from 'expo-router'
import { Alert, Platform, ScrollView, Text, View } from 'react-native'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { SafeAreaView } from 'react-native-safe-area-context'
import { ChevronLeft, Download, MessageSquare, RotateCcw } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { toast } from '@/components/ToastConfig'
import { fetchFeedbackExport, getCorrectionHistory, revertCorrection } from '@/src/api/analyze'
import { colors } from '@/src/constants/colors'
import { listLessonsJournal, listUserFeedback } from '@/src/db/client'
import type { FeedbackType, LessonListRow, UserFeedbackRow } from '@/src/db/types'
import { DEMO_LESSON_JOB_ID } from '@/src/demo/constants'
import { getOrCreateFeedbackUserId, useCorrectionStore } from '@/src/stores/correctionStore'
import { useLessonStore } from '@/src/stores/lessonStore'
import type { FeedbackExportResponse, FeedbackRecord } from '@/src/types'
import { shareExportedBlob } from '@/src/utils/exportShare'
import {
  FEEDBACK_TYPE_LABELS,
  buildFeedbackStats,
  dedupeFeedbackRows,
  parseFeedbackValues,
  summarizeFeedbackRows,
} from '@/src/utils/feedback'

type FeedbackJobGroup = {
  jobId: string
  rows: UserFeedbackRow[]
  latest: string
  total: number
  chord: number
  note: number
  wrong: number
}

function splitForType(type: FeedbackType): 'chord' | 'solo' {
  return type === 'note_correction' ? 'solo' : 'chord'
}

function formatEventValue(row: UserFeedbackRow): string {
  const original = parseFeedbackValues(row.original_value)
  const corrected = parseFeedbackValues(row.corrected_value)
  if (row.feedback_type === 'note_correction') {
    const from = typeof original?.pitch === 'number' ? `MIDI ${original.pitch}` : 'note'
    const to = typeof corrected?.pitch === 'number' ? `MIDI ${corrected.pitch}` : 'flagged'
    return `${from} → ${to}`
  }
  const from = typeof original?.chord === 'string' ? original.chord : 'chord'
  const to = typeof corrected?.chord === 'string' ? corrected.chord : 'flagged'
  return `${from} → ${to}`
}

function localExportPayload(
  rows: UserFeedbackRow[],
  split: 'chord' | 'solo',
  jobId: string | null,
): FeedbackExportResponse {
  const selected = rows.filter((row) => splitForType(row.feedback_type) === split)
  return {
    job_id: jobId ?? 'all',
    split,
    exported_at: new Date().toISOString(),
    records: selected.map<FeedbackRecord>((row) => ({
      id: row.id,
      job_id: row.job_id,
      song_id: row.song_id,
      feedback_type: row.feedback_type,
      event_index: row.event_index,
      original_value: parseFeedbackValues(row.original_value) ?? {},
      corrected_value: parseFeedbackValues(row.corrected_value),
      reason: row.reason,
      created_at: row.timestamp,
      reverted_at: null,
    })),
  }
}

async function shareFeedbackJson(
  payload: FeedbackExportResponse & { user_id?: string },
  filename: string,
): Promise<void> {
  await shareExportedBlob({
    blob: new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }),
    mimeType: 'application/json',
    contentDisposition: null,
    fallbackBase: filename,
    dialogTitle: 'Export feedback',
  })
}

export default function FeedbackDashboardScreen() {
  const router = useRouter()
  const [rows, setRows] = useState<UserFeedbackRow[]>([])
  const [lessons, setLessons] = useState<LessonListRow[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [exporting, setExporting] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [feedbackRows, lessonRows] = await Promise.all([listUserFeedback(), listLessonsJournal()])
      setRows(feedbackRows)
      setLessons(lessonRows)
    } catch (e) {
      toast.error(`Could not load feedback: ${e instanceof Error ? e.message : 'unknown error'}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const deduped = useMemo(() => dedupeFeedbackRows(rows), [rows])
  const stats = useMemo(() => buildFeedbackStats(deduped), [deduped])
  const lessonTitles = useMemo(
    () => new Map(lessons.map((lesson) => [lesson.job_id, lesson.song_title])),
    [lessons],
  )
  const jobs = useMemo<FeedbackJobGroup[]>(() => {
    const grouped = new Map<string, UserFeedbackRow[]>()
    for (const row of deduped) {
      const current = grouped.get(row.job_id) ?? []
      current.push(row)
      grouped.set(row.job_id, current)
    }
    return [...grouped.entries()]
      .map(([jobId, jobRows]) => {
        const counts = summarizeFeedbackRows(jobRows)
        return {
          jobId,
          rows: jobRows,
          latest: jobRows.reduce((latest, row) => (row.timestamp > latest ? row.timestamp : latest), ''),
          total: counts.total,
          chord: counts.chord_corrections,
          note: counts.note_corrections,
          wrong: counts.wrong_chords,
        }
      })
      .sort((a, b) => (a.latest < b.latest ? 1 : a.latest > b.latest ? -1 : 0))
  }, [deduped])

  const exportJob = useCallback(
    async (jobId: string, split: 'chord' | 'solo') => {
      const filename = `${split}_feedback_${jobId.replace(/[^\w.-]+/g, '_')}.json`
      setExporting(`${jobId}:${split}`)
      try {
        let payload: FeedbackExportResponse
        if (jobId === DEMO_LESSON_JOB_ID) {
          payload = localExportPayload(
            deduped.filter((row) => row.job_id === jobId),
            split,
            jobId,
          )
        } else {
          try {
            payload = await fetchFeedbackExport(jobId, split)
          } catch (e) {
            const fallback = localExportPayload(
              deduped.filter((row) => row.job_id === jobId),
              split,
              jobId,
            )
            toast.error(
              `Server export unavailable; exporting local records instead: ${
                e instanceof Error ? e.message : 'unknown error'
              }`,
            )
            payload = fallback
          }
        }
        await shareFeedbackJson(payload, filename)
        toast.success('Feedback export ready')
      } catch (e) {
        toast.error(`Export failed: ${e instanceof Error ? e.message : 'unknown error'}`)
      } finally {
        setExporting(null)
      }
    },
    [deduped],
  )

  const exportAll = useCallback(
    async (split: 'chord' | 'solo') => {
      setExporting(`all:${split}`)
      try {
        const userId = await getOrCreateFeedbackUserId()
        const payload = localExportPayload(deduped, split, null)
        await shareFeedbackJson({ ...payload, user_id: userId }, `${split}_feedback.json`)
        toast.success('Feedback export ready')
      } catch (e) {
        toast.error(`Export failed: ${e instanceof Error ? e.message : 'unknown error'}`)
      } finally {
        setExporting(null)
      }
    },
    [deduped],
  )

  const performRevert = useCallback(
    async (row: UserFeedbackRow) => {
      setBusyId(row.id)
      const errors: string[] = []
      const skipServer = row.job_id === DEMO_LESSON_JOB_ID
      try {
        await useCorrectionStore.getState().hydrate(row.job_id)
        const localCorrections = useCorrectionStore.getState().getCorrections(row.job_id)
        const localId =
          row.feedback_type === 'note_correction'
            ? localCorrections.noteCorrections.find((correction) => correction.noteIndex === row.event_index)?.id
            : localCorrections.chordCorrections.find((correction) => correction.eventIndex === row.event_index)?.id

        const result = await useCorrectionStore
          .getState()
          .revertFeedback(row, { syncToServer: !skipServer })
        if (result.syncError) errors.push(`feedback marker: ${result.syncError}`)
        if (localId) {
          await useCorrectionStore.getState().revertCorrection(row.job_id, localId)
        }

        if (!skipServer) {
          try {
            const history = await getCorrectionHistory(row.job_id)
            const targetType = row.feedback_type === 'note_correction' ? 'solo_note' : 'chord'
            let targetIndex = -1
            for (let index = history.corrections.length - 1; index >= 0; index -= 1) {
              const correction = history.corrections[index]
              if (correction?.correction_type === targetType && correction.index === row.event_index) {
                targetIndex = index
                break
              }
            }
            if (targetIndex >= 0) {
              await revertCorrection(row.job_id, targetIndex)
              useLessonStore.getState().requestScoreRefetch(row.job_id)
            }
          } catch (e) {
            errors.push(`score correction: ${e instanceof Error ? e.message : 'unknown error'}`)
          }
        }

        await load()
        if (errors.length > 0) {
          toast.error(`Feedback removed locally. Server revert failed: ${errors.join('; ')}`)
        } else {
          toast.success('Feedback reverted')
        }
      } catch (e) {
        toast.error(`Could not revert feedback: ${e instanceof Error ? e.message : 'unknown error'}`)
      } finally {
        setBusyId(null)
      }
    },
    [load],
  )

  const confirmRevert = useCallback(
    (row: UserFeedbackRow) => {
      const detail = 'The feedback entry will be removed from this device and reverted on the server when available.'
      if (Platform.OS === 'web') {
        if (typeof window !== 'undefined' && window.confirm(`Revert this feedback?\n\n${detail}`)) {
          void performRevert(row)
        }
        return
      }
      Alert.alert('Revert feedback?', detail, [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Revert', style: 'destructive', onPress: () => void performRevert(row) },
      ])
    },
    [performRevert],
  )

  return (
    <SafeAreaView className="flex-1 bg-wood-900" edges={['top', 'left', 'right']}>
      <ScrollView className="flex-1 px-6 py-6" contentContainerStyle={{ paddingBottom: 40 }}>
        <View className="mb-5 flex-row items-center gap-3">
          <AnimatedPressable
            onPress={() => router.back()}
            haptic="light"
            className="rounded-full border border-wood-600/50 bg-wood-800/60 p-2"
            accessibilityRole="button"
            accessibilityLabel="Back to settings"
          >
            <ChevronLeft color={colors.cream} size={20} strokeWidth={2} />
          </AnimatedPressable>
          <View className="flex-1">
            <Text className="font-serif text-3xl text-cream">Feedback</Text>
            <Text className="mt-1 font-sans text-sm text-muted-light">
              Review reported chords and notes, or export training data.
            </Text>
          </View>
        </View>

        <View className="mb-5 flex-row flex-wrap gap-2">
          <StatCard label="Total" value={stats.total} />
          <StatCard label="Chord" value={stats.chord_corrections} />
          <StatCard label="Note" value={stats.note_corrections} />
          <StatCard label="Flagged" value={stats.wrong_chords} />
        </View>

        {stats.most_corrected_chords.length > 0 ? (
          <View className="mb-5 rounded-xl border border-wood-600/40 bg-wood-800/50 p-3">
            <Text className="font-sans-medium text-[10px] uppercase tracking-wide text-amber-light">
              Most corrected chords
            </Text>
            <Text className="mt-1 font-sans text-sm text-cream">
              {stats.most_corrected_chords
                .map((item) => `${item.chord} (${item.count})`)
                .join(' · ')}
            </Text>
          </View>
        ) : null}

        <View className="mb-5 flex-row gap-2">
          <AnimatedPressable
            onPress={() => void exportAll('chord')}
            disabled={exporting != null || deduped.length === 0}
            haptic="light"
            className="flex-1 flex-row items-center justify-center gap-2 rounded-lg border border-amber-accent/50 bg-amber-accent/15 px-3 py-2.5 disabled:opacity-50"
            accessibilityRole="button"
          >
            <Download color={colors.amber.accent} size={16} strokeWidth={2} />
            <Text className="font-sans-medium text-xs text-amber-light">
              {exporting === 'all:chord' ? 'Exporting…' : 'Export chords'}
            </Text>
          </AnimatedPressable>
          <AnimatedPressable
            onPress={() => void exportAll('solo')}
            disabled={exporting != null || deduped.length === 0}
            haptic="light"
            className="flex-1 flex-row items-center justify-center gap-2 rounded-lg border border-amber-accent/50 bg-amber-accent/15 px-3 py-2.5 disabled:opacity-50"
            accessibilityRole="button"
          >
            <Download color={colors.amber.accent} size={16} strokeWidth={2} />
            <Text className="font-sans-medium text-xs text-amber-light">
              {exporting === 'all:solo' ? 'Exporting…' : 'Export solo'}
            </Text>
          </AnimatedPressable>
        </View>

        {loading ? (
          <Text className="font-sans text-sm text-muted-light">Loading feedback…</Text>
        ) : jobs.length === 0 ? (
          <View className="items-center rounded-2xl border border-wood-600/40 bg-wood-800/40 px-6 py-10">
            <MessageSquare color={colors.amber.accent} size={32} strokeWidth={1.5} />
            <Text className="mt-3 font-serif text-lg text-cream">No feedback yet</Text>
            <Text className="mt-1 text-center font-sans text-xs text-muted-light">
              Use “Report incorrect” or correct a chord/note during a session to see entries here.
            </Text>
          </View>
        ) : (
          jobs.map((job) => (
            <View key={job.jobId} className="mb-4 rounded-2xl border border-wood-600/50 bg-wood-800/50 p-4">
              <View className="flex-row items-start justify-between gap-3">
                <View className="flex-1">
                  <Text className="font-serif text-lg text-cream">
                    {lessonTitles.get(job.jobId)?.trim() || 'Analyzed song'}
                  </Text>
                  <Text className="mt-0.5 font-mono text-[10px] text-muted-light">{job.jobId}</Text>
                  <Text className="mt-1 font-sans text-[11px] text-muted-light">
                    {job.total} report{job.total === 1 ? '' : 's'} · {job.chord} chord · {job.note} note ·{' '}
                    {job.wrong} flagged
                  </Text>
                </View>
              </View>

              <View className="mt-3 flex-row gap-2">
                <AnimatedPressable
                  onPress={() => void exportJob(job.jobId, 'chord')}
                  disabled={exporting != null}
                  className="flex-1 rounded-lg border border-wood-600/50 bg-wood-900/40 px-3 py-2 disabled:opacity-50"
                  accessibilityRole="button"
                >
                  <Text className="text-center font-sans-medium text-[11px] text-cream">
                    {exporting === `${job.jobId}:chord` ? 'Exporting…' : 'Export chords'}
                  </Text>
                </AnimatedPressable>
                <AnimatedPressable
                  onPress={() => void exportJob(job.jobId, 'solo')}
                  disabled={exporting != null}
                  className="flex-1 rounded-lg border border-wood-600/50 bg-wood-900/40 px-3 py-2 disabled:opacity-50"
                  accessibilityRole="button"
                >
                  <Text className="text-center font-sans-medium text-[11px] text-cream">
                    {exporting === `${job.jobId}:solo` ? 'Exporting…' : 'Export solo'}
                  </Text>
                </AnimatedPressable>
              </View>

              <View className="mt-3 gap-2">
                {job.rows.map((row) => (
                  <View
                    key={row.id}
                    className="flex-row items-center gap-3 rounded-xl border border-wood-600/35 bg-wood-900/40 p-3"
                  >
                    <View className="flex-1">
                      <Text className="font-sans-medium text-[11px] text-amber-light">
                        {FEEDBACK_TYPE_LABELS[row.feedback_type]} · event {row.event_index + 1}
                      </Text>
                      <Text className="mt-1 font-mono text-xs text-cream">{formatEventValue(row)}</Text>
                      <Text className="mt-1 font-sans text-[10px] text-muted-light">
                        {new Date(row.timestamp).toLocaleString()}
                        {row.reason ? ` · ${row.reason}` : ''}
                      </Text>
                    </View>
                    <AnimatedPressable
                      onPress={() => confirmRevert(row)}
                      disabled={busyId === row.id}
                      haptic="light"
                      className="rounded-full border border-danger/40 bg-danger/10 p-2 disabled:opacity-50"
                      accessibilityRole="button"
                      accessibilityLabel="Revert feedback"
                    >
                      <RotateCcw color={colors.danger} size={16} strokeWidth={2} />
                    </AnimatedPressable>
                  </View>
                ))}
              </View>
            </View>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <View className="min-w-[72px] flex-1 rounded-lg border border-wood-600/50 bg-wood-800/60 p-3">
      <Text className="font-serif text-2xl text-amber-light">{value}</Text>
      <Text className="mt-1 font-sans text-[10px] uppercase tracking-wider text-muted-light">{label}</Text>
    </View>
  )
}
