import { useRouter } from 'expo-router'
import { useMemo } from 'react'
import { Text, View } from 'react-native'

import { SessionStemAndTab } from '@/components/SessionStemAndTab'
import { SessionStepScreen } from '@/components/SessionStepScreen'
import { sessionHref } from '@/src/constants/sessionFlow'
import { useMetronomeDefaultOn } from '@/src/settings/useMetronomeDefaultOn'
import { useLessonStore } from '@/src/stores/lessonStore'
import { parseSectionRecord } from '@/src/utils/lessonAudio'

type LoopRegion = { startSec: number; endSec: number; label: string; source: string }

function asNumber(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    const n = Number.parseFloat(v)
    if (Number.isFinite(n)) return n
  }
  return null
}

function barToWindow(barTimestamps: number[], barIndex: number, fallbackBeatSec: number): LoopRegion | null {
  if (barTimestamps.length === 0) return null
  const i = Math.max(0, Math.min(barIndex, barTimestamps.length - 1))
  const startSec = barTimestamps[i]!
  const next = i + 1 < barTimestamps.length ? barTimestamps[i + 1]! : startSec + Math.max(0.4, fallbackBeatSec * 4)
  const endSec = Math.max(startSec + 0.2, next)
  return { startSec, endSec, label: `Bar ${i + 1}`, source: 'bar' }
}

function firstChorusWindow(sections: Array<Record<string, unknown>>, fallbackBeatSec: number): LoopRegion | null {
  const chorusIndex = sections.findIndex((s) => {
    const raw = typeof s.label === 'string' ? s.label : ''
    return raw.toLowerCase().includes('chorus')
  })
  if (chorusIndex < 0) return null
  const here = parseSectionRecord(sections[chorusIndex]).startTimeSeconds
  if (here == null) return null
  const next = chorusIndex + 1 < sections.length ? parseSectionRecord(sections[chorusIndex + 1]).startTimeSeconds : null
  const span = Math.max(0.6, fallbackBeatSec * 4)
  return {
    startSec: here,
    endSec: next != null && next > here ? Math.min(next, here + span) : here + span,
    label: 'First chorus',
    source: 'chorus',
  }
}

function deriveSlowLoopRegion(
  section: Record<string, unknown> | undefined,
  sections: Array<Record<string, unknown>>,
  barTimestamps: number[],
  tempo: number | null | undefined,
): LoopRegion | null {
  const beatSec = tempo && tempo > 0 ? 60 / tempo : 0.5
  const sec = section ?? {}

  const barKeys = ['hardest_bar_index', 'hardestBarIndex', 'hardest_bar', 'hardestBar', 'loop_bar', 'loopBar']
  for (const key of barKeys) {
    const n = asNumber(sec[key])
    if (n != null) {
      const out = barToWindow(barTimestamps, Math.floor(n), beatSec)
      if (out) return { ...out, source: `section.${key}` }
    }
  }

  const rangeKeys: Array<[string, string]> = [
    ['loop_start_bar', 'loop_end_bar'],
    ['loopStartBar', 'loopEndBar'],
    ['hardest_start_bar', 'hardest_end_bar'],
    ['hardestStartBar', 'hardestEndBar'],
  ]
  for (const [a, b] of rangeKeys) {
    const startBar = asNumber(sec[a])
    const endBar = asNumber(sec[b])
    if (startBar != null) {
      const start = Math.floor(startBar)
      const end = Math.max(start + 1, Math.floor(endBar ?? start + 1))
      if (barTimestamps.length > 0) {
        const startSec = barTimestamps[Math.max(0, Math.min(start, barTimestamps.length - 1))]!
        const endSec =
          end < barTimestamps.length ? barTimestamps[end]! : startSec + Math.max(0.4, beatSec * 4)
        return {
          startSec,
          endSec: Math.max(startSec + 0.2, endSec),
          label: `Bars ${start + 1}-${end}`,
          source: `section.${a}/${b}`,
        }
      }
    }
  }

  const density = sec.note_density_by_bar
  if (Array.isArray(density) && density.length > 0 && barTimestamps.length > 0) {
    let bestI = 0
    let bestV = -1
    density.forEach((v, i) => {
      const n = asNumber(v)
      if (n != null && n > bestV) {
        bestV = n
        bestI = i
      }
    })
    const out = barToWindow(barTimestamps, bestI, beatSec)
    if (out) return { ...out, source: 'section.note_density_by_bar' }
  }

  const chorus = firstChorusWindow(sections, beatSec)
  if (chorus) return chorus

  const currentStart = parseSectionRecord(sec).startTimeSeconds
  if (currentStart != null) {
    return {
      startSec: currentStart,
      endSec: currentStart + Math.max(0.6, beatSec * 4),
      label: 'Current section start',
      source: 'section.start_time_seconds fallback',
    }
  }

  if (barTimestamps.length > 0) {
    const out = barToWindow(barTimestamps, 0, beatSec)
    if (out) return { ...out, source: 'bar_timestamps[0] fallback' }
  }

  return null
}

export default function SlowScreen() {
  const router = useRouter()
  const initialMetronomeOn = useMetronomeDefaultOn()
  const lesson = useLessonStore((s) => s.lesson)
  const lessonSectionIndex = useLessonStore((s) => s.lessonSectionIndex)

  const sections = (lesson?.sections ?? []) as Array<Record<string, unknown>>
  const section = sections[lessonSectionIndex]
  const loopRegion = useMemo(
    () => deriveSlowLoopRegion(section, sections, lesson?.bar_timestamps ?? [], lesson?.tempo),
    [lesson?.bar_timestamps, lesson?.tempo, lessonSectionIndex, sections, section],
  )

  return (
    <SessionStepScreen
      title="Slow"
      subtitle="Starts at 65% speed, pre-loops the hardest detected target, and keeps cursor synced to slowed audio."
      showBack
      onBack={() => router.back()}
      showNext
      nextLabel="Next: Play"
      onNext={() => router.push(sessionHref('play'))}
    >
      {loopRegion ? (
        <View className="rounded-lg border border-wood-600/45 bg-cream-dark/45 px-3 py-2">
          <Text className="font-sans text-xs text-wood-900">
            Slow target: {loopRegion.label} ({loopRegion.startSec.toFixed(1)}s - {loopRegion.endSec.toFixed(1)}s)
          </Text>
          <Text className="mt-1 font-mono text-[10px] text-muted-brown">Source: {loopRegion.source}</Text>
        </View>
      ) : null}
      <SessionStemAndTab
        initialRate={0.65}
        initialMetronomeOn={initialMetronomeOn}
        autoLoopRegion={loopRegion ? { startSec: loopRegion.startSec, endSec: loopRegion.endSec, label: loopRegion.label } : null}
      />
    </SessionStepScreen>
  )
}
