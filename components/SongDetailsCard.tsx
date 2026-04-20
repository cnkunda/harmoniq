import { useMemo, useState } from 'react'
import { Text, useWindowDimensions, View } from 'react-native'
import Animated, { FadeIn } from 'react-native-reanimated'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { CoachNote } from '@/components/CoachNote'
import { LoadingSkeleton } from '@/components/LoadingSkeleton'
import type { LessonJSON } from '@/src/types'
import type { SongScoreMeta } from '@/types/tabMessage'

function lessonSectionLabel(lesson: LessonJSON | null | undefined, idx: number): string | null {
  const raw = lesson?.sections?.[idx]
  if (!raw || typeof raw !== 'object') return null
  const lab = (raw as Record<string, unknown>).label
  return typeof lab === 'string' && lab.trim() ? lab.trim() : null
}

function dashOr(v: string | null | undefined): string {
  if (v != null && String(v).trim()) return String(v).trim()
  return '—'
}

export type SongDetailsCardProps = {
  lesson: LessonJSON | null
  scoreMeta: SongScoreMeta | null
  playback: { masterBarIndex: number; sectionLabel: string | null } | null
  lessonSectionIndex: number
}

export function SongDetailsCard({
  lesson,
  scoreMeta,
  playback,
  lessonSectionIndex,
}: SongDetailsCardProps) {
  const { width } = useWindowDimensions()
  const compact = width < 520
  const [expanded, setExpanded] = useState(!compact)

  const merged = useMemo(() => {
    const apiTitle = lesson?.song_title?.trim() || null
    const scTitle = scoreMeta?.title?.trim() || null
    const title = apiTitle || scTitle || null

    const apiArtist = lesson?.artist?.trim() || null
    const scArtist = scoreMeta?.artist?.trim() || null
    const artist = apiArtist || scArtist || null

    const key = lesson?.key?.trim() || null

    let tempoLine: string | null = null
    if (typeof lesson?.tempo === 'number' && Number.isFinite(lesson.tempo) && lesson.tempo > 0) {
      tempoLine = `${Math.round(lesson.tempo)} BPM`
    } else if (
      typeof scoreMeta?.tempoBpm === 'number' &&
      Number.isFinite(scoreMeta.tempoBpm) &&
      scoreMeta.tempoBpm > 0
    ) {
      tempoLine = `${Math.round(scoreMeta.tempoBpm)} BPM`
    }

    const sectionLive = playback?.sectionLabel?.trim() || null
    const sectionLesson = lessonSectionLabel(lesson, lessonSectionIndex)
    const section = sectionLive || sectionLesson || null

    let confidenceLine: string | null = null
    const tc = lesson?.transcription_confidence
    if (typeof tc === 'number' && Number.isFinite(tc)) {
      const pct = Math.round(Math.max(0, Math.min(1, tc)) * 100)
      confidenceLine = `${pct}%`
    }

    return { title, artist, key, tempoLine, section, confidenceLine }
  }, [lesson, lessonSectionIndex, playback, scoreMeta])

  const summaryTitle = dashOr(merged.title) === '—' ? 'Song details' : (merged.title ?? 'Song details')
  const sectionCoach = useMemo(() => {
    const raw = lesson?.sections?.[lessonSectionIndex]
    if (!raw || typeof raw !== 'object') return { note: '', explanation: '' }
    const o = raw as Record<string, unknown>
    return {
      note: typeof o.coach_note === 'string' ? o.coach_note.trim() : '',
      explanation: typeof o.coach_explanation === 'string' ? o.coach_explanation.trim() : '',
    }
  }, [lesson, lessonSectionIndex])
  const coachReady = !!sectionCoach.note && !!sectionCoach.explanation

  return (
    <View className="mb-2 rounded-lg border border-wood-600/40 bg-cream-dark/50 px-3 py-2">
      <AnimatedPressable
        haptic="light"
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={() => setExpanded((e) => !e)}
        className="flex-row items-center justify-between gap-2"
      >
        <View className="min-w-0 flex-1">
          <Text className="font-sans-medium text-sm text-wood-900" numberOfLines={compact && !expanded ? 1 : 3}>
            {summaryTitle}
          </Text>
          {compact && !expanded ? (
            <Text className="mt-0.5 font-sans text-[11px] text-muted-brown" numberOfLines={1}>
              {dashOr(merged.section)} · {merged.tempoLine ?? '—'}
            </Text>
          ) : null}
        </View>
        <Text className="font-sans text-xs text-muted-brown">{expanded ? '▼' : '▶'}</Text>
      </AnimatedPressable>

      {expanded ? (
        <View className="mt-2 gap-1 border-t border-wood-600/25 pt-2">
          <Text className="font-sans text-[12px] text-wood-900">
            <Text className="font-sans-medium text-muted-brown">Title: </Text>
            {dashOr(merged.title)}
          </Text>
          <Text className="font-sans text-[12px] text-wood-900">
            <Text className="font-sans-medium text-muted-brown">Artist: </Text>
            {dashOr(merged.artist)}
          </Text>
          <Text className="font-sans text-[12px] text-wood-900">
            <Text className="font-sans-medium text-muted-brown">Tempo: </Text>
            {merged.tempoLine ?? '—'}
          </Text>
          <Text className="font-sans text-[12px] text-wood-900">
            <Text className="font-sans-medium text-muted-brown">Key: </Text>
            {dashOr(merged.key)}
          </Text>
          <Text className="font-sans text-[12px] text-wood-900">
            <Text className="font-sans-medium text-muted-brown">Section: </Text>
            {dashOr(merged.section)}
          </Text>
          <Text className="font-sans text-[12px] text-wood-900">
            <Text className="font-sans-medium text-muted-brown">Transcription confidence: </Text>
            {merged.confidenceLine ?? '—'}
          </Text>
          <View className="mt-2 min-h-[124px]">
            <Text className="mb-2 font-sans-medium text-[12px] uppercase tracking-wide text-muted-brown">Coach</Text>
            {coachReady ? (
              <Animated.View entering={FadeIn.duration(220)}>
                <CoachNote text={sectionCoach.note} />
                <Text className="mt-2 px-1 font-sans text-[12px] leading-5 text-wood-900">{sectionCoach.explanation}</Text>
              </Animated.View>
            ) : (
              <View className="rounded-xl border border-wood-600/45 bg-wood-700/70 p-4">
                <LoadingSkeleton height={14} width="72%" borderRadius={6} />
                <LoadingSkeleton height={12} width="92%" borderRadius={6} style={{ marginTop: 8 }} />
                <LoadingSkeleton height={12} width="88%" borderRadius={6} style={{ marginTop: 6 }} />
              </View>
            )}
          </View>
        </View>
      ) : null}
    </View>
  )
}
