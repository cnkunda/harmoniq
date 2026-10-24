import { useEffect, useRef } from 'react'
import { ScrollView, Text, View } from 'react-native'

import { colors } from '@/src/constants/colors'
import type { PulseBar } from '@/src/progress/pulseData'

const BAR_WIDTH = 68
const BAR_GAP = 6

export interface PulseChordTimelineProps {
  bars: readonly PulseBar[]
  activeIndex: number
}

export function PulseChordTimeline({ bars, activeIndex }: PulseChordTimelineProps) {
  const scrollRef = useRef<ScrollView>(null)

  useEffect(() => {
    if (activeIndex < 0 || bars.length === 0) return
    const x = Math.max(0, activeIndex * (BAR_WIDTH + BAR_GAP) - BAR_WIDTH * 2)
    scrollRef.current?.scrollTo({ x, animated: true })
  }, [activeIndex, bars.length])

  return (
    <View className="mt-4">
      <View className="mb-2 flex-row items-center justify-between">
        <Text className="font-sans-medium text-[11px] uppercase tracking-wider text-muted-light">
          Chord timeline
        </Text>
        <Text className="font-mono text-[11px] text-muted-light/80">
          {bars.length > 0 && activeIndex >= 0
            ? `Bar ${Math.min(activeIndex + 1, bars.length)} of ${bars.length}`
            : 'No bars'}
        </Text>
      </View>

      {bars.length === 0 ? (
        <View className="rounded-lg border border-wood-600/40 bg-wood-900/40 px-4 py-5">
          <Text className="font-sans text-xs text-muted-light">
            Analyze a song to populate the chord timeline.
          </Text>
        </View>
      ) : (
        <ScrollView
          ref={scrollRef}
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingRight: 12 }}
        >
          {bars.map((bar) => {
            const isActive = bar.index === activeIndex
            return (
              <View
                key={`bar-${bar.index}`}
                accessible
                accessibilityRole="text"
                accessibilityLabel={`Bar ${bar.index + 1}, ${bar.display}${bar.roman ? `, ${bar.roman}` : ''}`}
                className={`mr-1.5 rounded-lg border px-2.5 py-2 ${
                  isActive
                    ? 'border-amber-accent bg-amber-accent/15'
                    : 'border-wood-600/45 bg-wood-800/45'
                }`}
                style={{ width: BAR_WIDTH }}
              >
                <View className="flex-row items-baseline justify-between">
                  <Text
                    className={`font-serif text-lg ${isActive ? 'text-amber-light' : 'text-cream/90'}`}
                    numberOfLines={1}
                  >
                    {bar.display}
                  </Text>
                  <Text className="font-mono text-[9px] text-muted-light/70">{bar.roman ?? ''}</Text>
                </View>
                <View className="mt-1 flex-row items-center gap-1">
                  <View
                    className="h-1 flex-1 rounded-full"
                    style={{ backgroundColor: `${colors.wood[900]}55` }}
                  >
                    <View
                      className="h-1 rounded-full"
                      style={{
                        width: `${Math.round(bar.confidence * 100)}%`,
                        backgroundColor: isActive ? colors.amber.light : colors.muted.light,
                      }}
                    />
                  </View>
                  <Text className="font-mono text-[9px] text-muted-light/70">
                    {Math.round(bar.confidence * 100)}
                  </Text>
                </View>
              </View>
            )
          })}
        </ScrollView>
      )}
    </View>
  )
}
