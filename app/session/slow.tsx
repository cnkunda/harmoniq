import { useRouter } from 'expo-router'
import { useEffect, useMemo, useState } from 'react'
import { Text, View } from 'react-native'

import { LoopRegionControl } from '@/components/LoopRegionControl'
import { SessionStemAndTab } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'
import { barRangeToSeconds } from '@/src/music/barLoopBounds'
import { useMetronomeDefaultOn } from '@/src/settings/useMetronomeDefaultOn'
import { deriveSlowLoopRegion } from '@/src/session/slowLoopRegion'
import { useLessonStore } from '@/src/stores/lessonStore'
import type { TabLoopBarRegion } from '@/types/tabMessage'

export default function SlowScreen() {
  const router = useRouter()
  const initialMetronomeOn = useMetronomeDefaultOn()
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)

  const sections = (lesson?.sections ?? []) as Array<Record<string, unknown>>
  const section = sections[lessonSectionIndex]
  const barTimestamps = lesson?.bar_timestamps ?? []
  const beatSec = lesson?.tempo && lesson.tempo > 0 ? 60 / lesson.tempo : 0.5

  const derived = useMemo(
    () => deriveSlowLoopRegion(section, sections, barTimestamps, lesson?.tempo),
    [barTimestamps, lesson?.tempo, lessonSectionIndex, section, sections],
  )

  const [loopBars, setLoopBars] = useState<TabLoopBarRegion | null>(null)

  useEffect(() => {
    if (!derived) {
      setLoopBars(null)
      return
    }
    setLoopBars({
      startBarIndex: derived.startBarIndex,
      endBarIndexExclusive: derived.endBarIndexExclusive,
    })
  }, [derived?.endBarIndexExclusive, derived?.startBarIndex, lesson?.job_id, lessonSectionIndex])

  const playbackLoop = useMemo(() => {
    if (loopBars && barTimestamps.length > 0) {
      const r = barRangeToSeconds(barTimestamps, loopBars.startBarIndex, loopBars.endBarIndexExclusive, beatSec)
      if (r) {
        return {
          startSec: r.startSec,
          endSec: r.endSec,
          label: `Bars ${loopBars.startBarIndex + 1}–${loopBars.endBarIndexExclusive}`,
        }
      }
    }
    if (derived) {
      return {
        startSec: derived.startSec,
        endSec: derived.endSec,
        label: derived.label,
      }
    }
    return null
  }, [barTimestamps, beatSec, derived, loopBars])

  const loopHighlight: TabLoopBarRegion | null =
    loopBars && barTimestamps.length > 0 ? loopBars : null

  return (
    <SessionStepScreen
      title="Slow"
      subtitle="Starts at 65% speed, loops a bar-aligned region, and keeps the tab cursor synced to slowed stems."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Play"
      onNext={() => router.push(sessionHref('play'))}
    >
      {playbackLoop ? (
        <View className="rounded-lg border border-wood-600/45 bg-cream-dark/45 px-3 py-2">
          <Text className="font-sans text-xs text-wood-900">
            Slow loop: {playbackLoop.label} ({playbackLoop.startSec.toFixed(2)}s – {playbackLoop.endSec.toFixed(2)}s)
          </Text>
          {__DEV__ && derived ? (
            <Text className="mt-1 font-mono text-[10px] text-muted-brown">Source: {derived.source}</Text>
          ) : null}
        </View>
      ) : null}

      {loopBars && barTimestamps.length >= 2 ? (
        <LoopRegionControl
          barCount={barTimestamps.length}
          value={loopBars}
          onChange={setLoopBars}
        />
      ) : null}

      <SessionStemAndTab
        initialRate={0.65}
        initialMetronomeOn={initialMetronomeOn}
        autoLoopRegion={playbackLoop}
        loopHighlight={loopHighlight}
      />
    </SessionStepScreen>
  )
}
