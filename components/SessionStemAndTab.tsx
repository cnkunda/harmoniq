import { useEffect, useMemo, useRef, useState } from 'react'
import { View } from 'react-native'

import { ListenStemPanel } from '@/components/ListenStemPanel'
import { TabViewport } from '@/components/TabViewport'
import { useSessionSmartScroll, type PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { useLessonStore } from '@/src/stores/lessonStore'
import type { AlphaTabSurfaceRef, NoteEventMessage, TabLoopBarRegion } from '@/types/tabMessage'
import { lessonStemUrl } from '@/src/utils/lessonAudio'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'

const DEFAULT_TICK: PlaybackTickContext = {
  positionSec: 0,
  playing: false,
  rate: 1,
  ready: false,
}

type SessionStemAndTabProps = {
  initialRate?: number
  initialMetronomeOn?: boolean
  autoLoopRegion?: { startSec: number; endSec: number; label?: string } | null
  /** Optional bar-range highlight on the score (Slow). */
  loopHighlight?: TabLoopBarRegion | null
  initialStemMuteById?: Record<string, boolean>
  onPlaybackTick?: (ctx: PlaybackTickContext) => void
  onNoteEvent?: (evt: NoteEventMessage) => void
}

/** Stems + GP tab with external-media cursor sync (commit 45). */
export function SessionStemAndTab({
  initialRate,
  initialMetronomeOn,
  autoLoopRegion,
  loopHighlight = null,
  initialStemMuteById,
  onPlaybackTick,
  onNoteEvent,
}: SessionStemAndTabProps) {
  const tabRef = useRef<AlphaTabSurfaceRef>(null)
  const tickRef = useRef<PlaybackTickContext>({ ...DEFAULT_TICK })

  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const section = lesson?.sections?.[lessonSectionIndex]
  const tabs = useMemo(() => readSectionTabPayloads(section), [section])
  const gp5Base64 = tabs.full ?? tabs.skeleton ?? null
  const audioSrc = useMemo(() => {
    const rel = lesson?.stems?.guitar
    if (!rel || typeof rel !== 'string') return null
    return lessonStemUrl(rel)
  }, [lesson?.stems?.guitar])
  const transposeSemitones =
    section && typeof section === 'object' && typeof (section as Record<string, unknown>).transposition_semitones === 'number'
      ? ((section as Record<string, unknown>).transposition_semitones as number)
      : 0

  const [scrollReset, setScrollReset] = useState(0)
  const [skewGen] = useState(0)

  useSessionSmartScroll({
    tabRef,
    barTimestamps: lesson?.bar_timestamps ?? [],
    tickRef,
    resetKey: scrollReset,
    skewDemoGeneration: skewGen,
  })

  const gp5Key = gp5Base64?.slice(0, 24) ?? ''

  useEffect(() => {
    const tab = tabRef.current
    if (!tab) return
    if (!loopHighlight || loopHighlight.startBarIndex >= loopHighlight.endBarIndexExclusive) {
      tab.setLoopRegion(null)
      return
    }
    tab.setLoopRegion(loopHighlight)
  }, [gp5Key, loopHighlight?.endBarIndexExclusive, loopHighlight?.startBarIndex])

  return (
    <>
      <ListenStemPanel
        initialRate={initialRate}
        initialMetronomeOn={initialMetronomeOn}
        autoLoopRegion={autoLoopRegion}
        initialStemMuteById={initialStemMuteById}
        onPlaybackTick={(ctx) => {
          tickRef.current = ctx
          if (ctx.ready) {
            tabRef.current?.syncPlaybackTimelineMs(ctx.positionSec * 1000)
          }
          onPlaybackTick?.(ctx)
        }}
        onSeek={() => setScrollReset((n) => n + 1)}
        onSeekSeconds={(seconds) => {
          tabRef.current?.seekTo(seconds * 1000)
        }}
        onRateChange={(rate) => {
          tabRef.current?.setPlaybackRate(rate)
        }}
      />
      {/* Fixed height: parent is in ScrollView (unbounded flex); flex-1 would collapse. */}
      <View className="mt-3 h-[320px] w-full">
        <TabViewport
          ref={tabRef}
          gp5Base64={gp5Base64}
          audioSrc={audioSrc}
          transposeSemitones={transposeSemitones}
          onNoteEvent={onNoteEvent}
          style={{ flex: 1, height: '100%', width: '100%' }}
        />
      </View>
    </>
  )
}
