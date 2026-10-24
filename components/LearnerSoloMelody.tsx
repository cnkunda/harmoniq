import { ScrollView, Text, View } from 'react-native'

import { midiToNoteName } from '@/src/music/scaleDegree'

export type LearnerSoloNote = {
  start_time: number
  duration: number
  pitch: number
  fret?: number
}

export type LearnerSoloMelodyProps = {
  notes: LearnerSoloNote[]
  barTimestamps?: number[] | null
  positionSec: number
}

function barIndexForTime(timestamps: number[] | null | undefined, timeSec: number): number {
  if (!timestamps || timestamps.length === 0) return 0
  let bar = 0
  for (let i = 0; i < timestamps.length; i += 1) {
    if (timestamps[i]! <= timeSec) bar = i
    else break
  }
  return bar
}

/** Commit 166: Learner notation — one-line solo melody instead of full score notation. */
export function LearnerSoloMelody({ notes, barTimestamps, positionSec }: LearnerSoloMelodyProps) {
  if (notes.length === 0) return null

  let previousBar = -1

  return (
    <View className="mt-3 rounded-xl border border-wood-600/40 bg-cream-dark/45 p-4">
      <View className="flex-row items-center justify-between">
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
          Solo melody
        </Text>
        <Text className="font-mono text-[10px] text-muted-brown">Single line</Text>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} className="mt-3">
        <View className="flex-row items-end gap-1.5 pr-4">
          {notes.map((note, index) => {
            const bar = barIndexForTime(barTimestamps, note.start_time)
            const showBar = bar !== previousBar
            previousBar = bar
            const isActive =
              positionSec >= note.start_time && positionSec < note.start_time + Math.max(note.duration, 0.05)
            const noteName = midiToNoteName(note.pitch)

            return (
              <View key={`solo-note-${index}`} className="flex-row items-end gap-1.5">
                {showBar ? (
                  <Text className="mb-1 font-mono text-[9px] text-muted-brown">|{bar + 1}</Text>
                ) : null}
                <View
                  className={`rounded-lg border px-2 py-1.5 ${
                    isActive
                      ? 'border-amber-accent bg-amber-accent/25'
                      : 'border-wood-600/30 bg-wood-800/40'
                  }`}
                >
                  <Text
                    className={`font-mono text-sm ${isActive ? 'text-amber-light' : 'text-cream'}`}
                  >
                    {noteName}
                  </Text>
                  {typeof note.fret === 'number' ? (
                    <Text className="mt-0.5 text-center font-mono text-[9px] text-muted-brown">
                      f{note.fret}
                    </Text>
                  ) : null}
                </View>
              </View>
            )
          })}
        </View>
      </ScrollView>
    </View>
  )
}
