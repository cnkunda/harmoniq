import { Text, View } from 'react-native'

import { NoteAccuracyBar } from '@/components/NoteAccuracyBar'
import type { NoteResultLabel } from '@/src/session/noteAccuracyBeats'
import type { TabNoteQueueEntry } from '@/src/session/usePlayCapture'

const VISIBLE = 7
const CENTER = Math.floor(VISIBLE / 2)

const CHIP_OFF = 'items-center justify-center rounded-full border border-wood-600/25 bg-white px-2 py-1.5'
const CHIP_ON =
  'min-w-[52px] items-center justify-center rounded-full border border-amber-accent bg-amber-accent px-3 py-2'

function countLabels(beats: NoteResultLabel[]) {
  let hit = 0
  let close = 0
  let miss = 0
  for (const b of beats) {
    if (b === 'hit' || b === 'vibrato') hit += 1
    else if (b === 'close') close += 1
    else if (b === 'miss') miss += 1
  }
  return { hit, close, miss }
}

export type PlayPitchBeatCardProps = {
  /** When true, no outer card chrome (nested inside playback strip column). */
  embedded?: boolean
  currentStreak: number
  adaptedCentsTolerance: number
  innerToleranceCents: number
  queue: TabNoteQueueEntry[]
  beats: NoteResultLabel[]
  noteLabels: string[]
  maxVisible?: number
}

/** Pitch target queue + per-beat accuracy in one compact panel (Play step). */
export function PlayPitchBeatCard({
  embedded = false,
  currentStreak,
  adaptedCentsTolerance,
  innerToleranceCents,
  queue,
  beats,
  noteLabels,
  maxVisible = 24,
}: PlayPitchBeatCardProps) {
  const nQueue = queue.length
  const currentIndex = Math.max(0, nQueue - 1)
  const slots: (TabNoteQueueEntry | null)[] = []
  for (let i = -CENTER; i <= CENTER; i += 1) {
    const idx = currentIndex + i
    if (idx >= 0 && idx < nQueue) slots.push(queue[idx]!)
    else slots.push(null)
  }

  const sliceLabels = noteLabels.length > maxVisible ? noteLabels.slice(-maxVisible) : noteLabels
  const sliceBeats = beats.length > maxVisible ? beats.slice(-maxVisible) : beats
  const nAlign = Math.min(sliceBeats.length, sliceLabels.length)
  const alignedLabels = sliceLabels.slice(-nAlign)
  const { hit, close, miss } = countLabels(beats.filter((b) => b !== 'ignored'))
  const scored = beats.filter((b) => b !== 'ignored').length
  const pct = scored > 0 ? Math.round(((hit + close) / scored) * 100) : null

  const shell = embedded
    ? 'min-h-0 flex-1 overflow-hidden'
    : 'overflow-hidden rounded-2xl border border-wood-600/45 bg-cream-dark/55 shadow-sm shadow-black/10'

  return (
    <View className={shell}>
      <View className="border-b border-wood-600/20 bg-cream px-3 py-2.5">
        <Text className="text-center font-mono text-[10px] leading-snug text-wood-600">
          Streak {currentStreak} beat{currentStreak === 1 ? '' : 's'} · ±{Math.round(adaptedCentsTolerance)}¢ adapts ·
          inner ≤{Math.round(innerToleranceCents)}¢
        </Text>
      </View>

      <View className="px-3 pb-3 pt-3">
        <View className="flex-row items-baseline justify-between gap-2">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-wood-600">Pitch targets</Text>
          {nQueue > 0 ? (
            <Text className="shrink font-mono text-[10px] text-wood-600">
              {nQueue} note{nQueue === 1 ? '' : 's'}
            </Text>
          ) : (
            <Text className="shrink font-mono text-[10px] text-wood-600">Tab…</Text>
          )}
        </View>

        <View className="mt-2.5 flex-row items-end justify-center gap-1.5">
          {slots.map((note, displayIdx) => {
            if (!note) {
              return <View key={`e-${displayIdx}`} className="h-12 w-8 shrink-0" />
            }
            const offset = displayIdx - CENTER
            const isCurrent = offset === 0
            const opacity = isCurrent ? 1 : Math.max(0.45, 1 - Math.abs(offset) * 0.18)
            return (
              <View
                key={`${note.midi}-${note.beat}-${displayIdx}`}
                className={isCurrent ? CHIP_ON : CHIP_OFF}
                style={{
                  opacity,
                  minHeight: isCurrent ? 52 : 40,
                }}
              >
                <Text
                  className={`font-mono font-semibold ${isCurrent ? 'text-lg text-wood-900' : 'text-sm text-wood-900'}`}
                >
                  {note.label}
                </Text>
                {isCurrent && note.string != null && note.fret != null ? (
                  <Text className="mt-0.5 font-mono text-[10px] text-wood-900/80">
                    s{note.string} · f{note.fret}
                  </Text>
                ) : null}
                {isCurrent ? (
                  <Text className="mt-1 font-sans-medium text-[9px] uppercase tracking-wide text-wood-900/90">Now</Text>
                ) : null}
              </View>
            )
          })}
        </View>
      </View>

      <View className="h-px bg-wood-600/20" />

      <View className="px-3 pb-3 pt-3">
        <View className="flex-row items-baseline justify-between gap-2">
          <Text className="font-sans-medium text-xs uppercase tracking-wide text-wood-600">Score · by beat</Text>
          {pct != null ? (
            <Text className="font-mono text-[10px] text-wood-900">{pct}% on-pitch</Text>
          ) : (
            <Text className="font-mono text-[10px] text-wood-600">—</Text>
          )}
        </View>
        <View className="mt-2">
          <NoteAccuracyBar beats={beats} maxVisible={maxVisible} />
        </View>
        {nAlign > 0 ? (
          <View className="mt-1.5 flex-row gap-0.5">
            {alignedLabels.map((label, i) => (
              <View key={`lb-${i}-${label}`} className="min-w-[6px] flex-1 items-center">
                <Text className="font-mono text-[8px] text-wood-600" numberOfLines={1}>
                  {label}
                </Text>
              </View>
            ))}
          </View>
        ) : null}
        <Text className="mt-1.5 font-sans text-[10px] text-wood-600">
          Hits {hit} · Close {close} · Miss {miss}
        </Text>
      </View>
    </View>
  )
}
