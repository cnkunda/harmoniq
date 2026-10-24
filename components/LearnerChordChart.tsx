import { ScrollView, Text, View } from 'react-native'

import { chordDifficulty, type ChordDifficulty } from '@/src/music/chordDifficulty'

export type LearnerChordBar = {
  chord: string
}

export type LearnerChordChartProps = {
  bars: LearnerChordBar[]
  currentBar?: number
}

const DIFFICULTY_TEXT: Record<ChordDifficulty, string> = {
  easy: 'text-success',
  medium: 'text-amber-light',
  hard: 'text-danger',
}

const DIFFICULTY_BORDER: Record<ChordDifficulty, string> = {
  easy: 'border-success/45 bg-success/10',
  medium: 'border-amber-accent/45 bg-amber-accent/10',
  hard: 'border-danger/45 bg-danger/10',
}

/** Commit 166: Learner notation — large chord symbols with color-coded difficulty. */
export function LearnerChordChart({ bars, currentBar }: LearnerChordChartProps) {
  const visibleBars = bars
    .map((bar, index) => ({ ...bar, index, difficulty: chordDifficulty(bar.chord) }))
    .filter((bar) => bar.chord.trim().length > 0)

  if (visibleBars.length === 0) {
    return (
      <View className="mt-3 rounded-xl border border-wood-600/40 bg-cream-dark/45 p-4">
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
          Chord chart
        </Text>
        <Text className="mt-2 font-sans text-sm text-muted-brown">
          No chord data yet for this section.
        </Text>
      </View>
    )
  }

  return (
    <View className="mt-3 rounded-xl border border-wood-600/40 bg-cream-dark/45 p-4">
      <View className="flex-row items-center justify-between">
        <Text className="font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
          Chord chart
        </Text>
        <Text className="font-mono text-[10px] text-muted-brown">Learner view</Text>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} className="mt-3">
        <View className="flex-row gap-2 pr-4">
          {visibleBars.map((bar) => {
            const isActive = currentBar === bar.index
            return (
              <View
                key={`learner-bar-${bar.index}`}
                className={`min-w-[92px] rounded-xl border px-3 py-2 ${
                  isActive ? 'border-amber-accent bg-amber-accent/20' : DIFFICULTY_BORDER[bar.difficulty]
                }`}
              >
                <Text className="font-mono text-[10px] text-muted-brown">Bar {bar.index + 1}</Text>
                <Text
                  className={`mt-1 font-serif text-3xl ${
                    isActive ? 'text-amber-light' : DIFFICULTY_TEXT[bar.difficulty]
                  }`}
                >
                  {bar.chord}
                </Text>
              </View>
            )
          })}
        </View>
      </ScrollView>

      <View className="mt-3 flex-row flex-wrap gap-3">
        <Text className="font-sans text-[11px] text-success">Easy</Text>
        <Text className="font-sans text-[11px] text-amber-light">Medium</Text>
        <Text className="font-sans text-[11px] text-danger">Hard</Text>
      </View>
    </View>
  )
}
