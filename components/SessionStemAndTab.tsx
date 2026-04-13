import type { ReactNode } from 'react'
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { View } from 'react-native'

import { ListenStemPanel, type ListenStemPanelHandle } from '@/components/ListenStemPanel'
import { TabViewport } from '@/components/TabViewport'
import { useSessionSmartScroll, type PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { useLessonStore } from '@/src/stores/lessonStore'
import { lessonStemUrl } from '@/src/utils/lessonAudio'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'
import type { AlphaTabSurfaceRef, NoteEventMessage, TabLoopBarRegion } from '@/types/tabMessage'

const DEFAULT_TICK: PlaybackTickContext = {
  positionSec: 0,
  playing: false,
  rate: 1,
  ready: false,
}

export type SessionTabVariant = 'full' | 'skeleton' | 'alt'

export type SessionStemAndTabProps = {
  initialRate?: number
  initialMetronomeOn?: boolean
  autoLoopRegion?: { startSec: number; endSec: number; label?: string } | null
  /** Optional bar-range highlight on the score (Slow). */
  loopHighlight?: TabLoopBarRegion | null
  initialStemMuteById?: Record<string, boolean>
  onPlaybackTick?: (ctx: PlaybackTickContext) => void
  onNoteEvent?: (evt: NoteEventMessage) => void
  /** Content between the stem panel and the tab (e.g. Study). */
  insertBetweenStemAndTab?: ReactNode
  /** Lesson tab variant; ignored when `gp5Base64Override` is set. */
  tabVariant?: SessionTabVariant
  /** Fixed GP5 (e.g. Jam) instead of the active lesson section. */
  gp5Base64Override?: string | null
  /** When false, only the tab viewport is shown (no `ListenStemPanel`). */
  showStemPanel?: boolean
  /** Optional stem URL when overriding GP5 or omitting lesson stems. */
  audioSrcOverride?: string | null
  transposeSemitonesOverride?: number
  onTabReady?: () => void
  onTabError?: (message: string) => void
  /** NativeWind classes for the tab wrapper. */
  tabFrameClassName?: string
}

export type SessionStemAndTabHandle = {
  seekTransportToSeconds: (sec: number) => Promise<void>
  scrollMasterBarIntoView: (barIndex: number) => void
  getTabSurface: () => AlphaTabSurfaceRef | null
}

/** Stems + GP tab with external-media cursor sync (commit 45). */
export const SessionStemAndTab = forwardRef<SessionStemAndTabHandle, SessionStemAndTabProps>(function SessionStemAndTab(
  {
    initialRate,
    initialMetronomeOn,
    autoLoopRegion,
    loopHighlight = null,
    initialStemMuteById,
    onPlaybackTick,
    onNoteEvent,
    insertBetweenStemAndTab,
    tabVariant,
    gp5Base64Override,
    showStemPanel = true,
    audioSrcOverride,
    transposeSemitonesOverride,
    onTabReady,
    onTabError,
    tabFrameClassName = 'mt-4 h-[328px] w-full px-2',
  },
  ref,
) {
  const tabRef = useRef<AlphaTabSurfaceRef>(null)
  const stemPanelRef = useRef<ListenStemPanelHandle>(null)
  const tickRef = useRef<PlaybackTickContext>({ ...DEFAULT_TICK })
  const lastStemPlayingRef = useRef(false)
  const lastTickPositionSecRef = useRef(0)

  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const section = lesson?.sections?.[lessonSectionIndex]
  const tabs = useMemo(() => readSectionTabPayloads(section), [section])

  const gp5Base64 = useMemo(() => {
    const o = gp5Base64Override?.trim()
    if (o) return o
    if (tabVariant === 'full') return tabs.full ?? null
    if (tabVariant === 'skeleton') return tabs.skeleton ?? null
    if (tabVariant === 'alt') return tabs.alt ?? null
    return tabs.full ?? tabs.skeleton ?? null
  }, [gp5Base64Override, tabVariant, tabs])

  const audioSrc = useMemo(() => {
    if (audioSrcOverride !== undefined) return audioSrcOverride
    if (gp5Base64Override?.trim()) return null
    const rel = lesson?.stems?.guitar
    if (!rel || typeof rel !== 'string') return null
    return lessonStemUrl(rel)
  }, [audioSrcOverride, gp5Base64Override, lesson?.stems?.guitar])

  const transposeSemitones =
    typeof transposeSemitonesOverride === 'number'
      ? transposeSemitonesOverride
      : section && typeof section === 'object' && typeof (section as Record<string, unknown>).transposition_semitones === 'number'
        ? ((section as Record<string, unknown>).transposition_semitones as number)
        : 0

  const [scrollReset, setScrollReset] = useState(0)

  useSessionSmartScroll({
    tabRef,
    barTimestamps: lesson?.bar_timestamps ?? [],
    tickRef,
    resetKey: scrollReset,
    pollIntervalMs: 200,
    enabled: showStemPanel,
  })

  const gp5Key = gp5Base64?.slice(0, 24) ?? ''

  useEffect(() => {
    lastStemPlayingRef.current = false
    lastTickPositionSecRef.current = 0
  }, [gp5Key])

  useEffect(() => {
    const tab = tabRef.current
    if (!tab) return
    if (!loopHighlight || loopHighlight.startBarIndex >= loopHighlight.endBarIndexExclusive) {
      tab.setLoopRegion(null)
      return
    }
    tab.setLoopRegion(loopHighlight)
  }, [gp5Key, loopHighlight?.endBarIndexExclusive, loopHighlight?.startBarIndex])

  useImperativeHandle(
    ref,
    () => ({
      seekTransportToSeconds: (sec: number) => stemPanelRef.current?.seekTransportToSeconds(sec) ?? Promise.resolve(),
      scrollMasterBarIntoView: (barIndex: number) => {
        tabRef.current?.scrollMasterBarIntoView(barIndex)
      },
      getTabSurface: () => tabRef.current,
    }),
    [],
  )

  return (
    <>
      {showStemPanel ? (
        <ListenStemPanel
          ref={stemPanelRef}
          initialRate={initialRate}
          initialMetronomeOn={initialMetronomeOn}
          autoLoopRegion={autoLoopRegion}
          initialStemMuteById={initialStemMuteById}
          onPlaybackTick={(ctx) => {
            const prevPosSec = lastTickPositionSecRef.current
            lastTickPositionSecRef.current = ctx.positionSec
            tickRef.current = ctx
            if (ctx.ready) {
              // Detect loop-wrap jumps (position moving backwards while still playing) and
              // force AlphaTab timeline reset so cursor/highlight/scroll stay stable on lap 2+.
              if (ctx.playing && ctx.positionSec + 0.12 < prevPosSec) {
                const wrapMs = Math.max(0, ctx.positionSec) * 1000
                setScrollReset((n) => n + 1)
                tabRef.current?.seekTo(wrapMs)
                tabRef.current?.syncPlaybackTimelineMs(wrapMs)
              }
              if (ctx.playing !== lastStemPlayingRef.current) {
                lastStemPlayingRef.current = ctx.playing
                tabRef.current?.setStemPlaybackActive(ctx.playing)
              }
              tabRef.current?.syncPlaybackTimelineMs(ctx.positionSec * 1000)
            }
            onPlaybackTick?.(ctx)
          }}
          onSeek={() => setScrollReset((n) => n + 1)}
          onSeekSeconds={(seconds) => {
            const ms = Math.max(0, seconds) * 1000
            tabRef.current?.seekTo(ms)
            tabRef.current?.syncPlaybackTimelineMs(ms)
          }}
          onRateChange={(rate) => {
            tabRef.current?.setPlaybackRate(rate)
          }}
        />
      ) : null}
      {insertBetweenStemAndTab}
      <View className={tabFrameClassName}>
        <TabViewport
          ref={tabRef}
          gp5Base64={gp5Base64}
          audioSrc={audioSrc}
          transposeSemitones={transposeSemitones}
          onReady={onTabReady}
          onError={onTabError}
          onNoteEvent={onNoteEvent}
          onScoreSeekMs={
            showStemPanel ? (ms) => void stemPanelRef.current?.seekTransportToSeconds(ms / 1000) : undefined
          }
          style={{ flex: 1, height: '100%', width: '100%' }}
        />
      </View>
    </>
  )
})
