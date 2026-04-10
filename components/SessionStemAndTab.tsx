import { useMemo, useRef, useState } from 'react'
import { Pressable, Text, View } from 'react-native'

import { ListenStemPanel } from '@/components/ListenStemPanel'
import { TabViewport } from '@/components/TabViewport'
import { useSessionSmartScroll, type PlaybackTickContext } from '@/src/session/useSessionSmartScroll'
import { useLessonStore } from '@/src/stores/lessonStore'
import type { AlphaTabSurfaceRef } from '@/types/tabMessage'
import { readSectionTabPayloads } from '@/src/utils/lessonTabs'

const DEFAULT_TICK: PlaybackTickContext = {
  positionSec: 0,
  playing: false,
  rate: 1,
  ready: false,
}

type SessionStemAndTabProps = {
  /** Dev control: one-shot wrong-bar scroll then correction (PRIORITIES §23). */
  showSkewDemoButton?: boolean
  initialRate?: number
  initialMetronomeOn?: boolean
  autoLoopRegion?: { startSec: number; endSec: number; label?: string } | null
  initialStemMuteById?: Record<string, boolean>
  onPlaybackTick?: (ctx: PlaybackTickContext) => void
}

/**
 * Stems + GP tab + SmartScroll (bar_timestamps ↔ mixer clock → scrollToBar).
 */
export function SessionStemAndTab({
  showSkewDemoButton = true,
  initialRate,
  initialMetronomeOn,
  autoLoopRegion,
  initialStemMuteById,
  onPlaybackTick,
}: SessionStemAndTabProps) {
  const tabRef = useRef<AlphaTabSurfaceRef>(null)
  const tickRef = useRef<PlaybackTickContext>({ ...DEFAULT_TICK })

  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)
  const section = lesson?.sections?.[lessonSectionIndex]
  const tabs = useMemo(() => readSectionTabPayloads(section), [section])
  const gp5Base64 = tabs.full ?? tabs.skeleton ?? null
  const transposeSemitones =
    section && typeof section === 'object' && typeof (section as Record<string, unknown>).transposition_semitones === 'number'
      ? ((section as Record<string, unknown>).transposition_semitones as number)
      : 0

  const [scrollReset, setScrollReset] = useState(0)
  const [skewGen, setSkewGen] = useState(0)

  useSessionSmartScroll({
    tabRef,
    barTimestamps: lesson?.bar_timestamps ?? [],
    tickRef,
    resetKey: scrollReset,
    skewDemoGeneration: skewGen,
  })

  return (
    <>
      <ListenStemPanel
        initialRate={initialRate}
        initialMetronomeOn={initialMetronomeOn}
        autoLoopRegion={autoLoopRegion}
        initialStemMuteById={initialStemMuteById}
        onPlaybackTick={(ctx) => {
          tickRef.current = ctx
          onPlaybackTick?.(ctx)
        }}
        onSeek={() => setScrollReset((n) => n + 1)}
      />
      {showSkewDemoButton ? (
        <View className="mt-2">
          <Pressable
            onPress={() => setSkewGen((g) => g + 1)}
            className="self-start rounded-lg border border-wood-600/50 bg-cream-dark/50 px-3 py-2"
            accessibilityRole="button"
          >
            <Text className="font-sans text-xs text-wood-900">
              SmartScroll: simulate clock skew (once)
            </Text>
          </Pressable>
          <Text className="mt-1 font-sans text-[11px] text-muted-brown">
            Plays a wrong bar (+180ms timeline), then jumps back — use while audio is playing.
          </Text>
        </View>
      ) : null}
      {/* Fixed height: parent is in ScrollView (unbounded flex); flex-1 would collapse. */}
      <View className="mt-3 h-[320px] w-full">
        <TabViewport
          ref={tabRef}
          gp5Base64={gp5Base64}
          transposeSemitones={transposeSemitones}
          style={{ flex: 1, height: '100%', width: '100%' }}
        />
      </View>
    </>
  )
}
