import { useRef } from 'react'
import { ScrollView, View, Text } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { useMusicState } from '@/src/context/MusicContext'
import type { ChordEvent } from '@/src/types'
import { formatChordDisplay } from '@/src/music/chordVoicing'

type ChordStripProps = {
  chordEvents: ChordEvent[]
  barTimestamps: number[]
  onChordTap?: (eventIndex: number, chord: string) => void
}

/**
 * Horizontal scrollable chord strip showing chord symbols aligned to bars.
 * Used in the Listen screen below the metronome card.
 */
export function ChordStrip({ chordEvents, barTimestamps, onChordTap }: ChordStripProps) {
  const musicState = useMusicState()
  const scrollRef = useRef<ScrollView>(null)

  if (!chordEvents.length) return null

  // Build bar → chord mapping
  const barChords: Array<{ bar: number; chord: string; eventIndex: number }> = []
  for (let bi = 0; bi < barTimestamps.length; bi++) {
    const barTime = barTimestamps[bi]
    // Find the latest chord event at or before this bar
    let bestIdx = 0
    for (let ci = 0; ci < chordEvents.length; ci++) {
      if (chordEvents[ci].timestamp <= barTime) bestIdx = ci
      else break
    }
    barChords.push({
      bar: bi,
      chord: chordEvents[bestIdx].chord,
      eventIndex: bestIdx,
    })
  }

  const currentBar = musicState.currentBar

  return (
    <View className="mb-2">
      <ScrollView
        ref={scrollRef}
        horizontal
        showsHorizontalScrollIndicator={false}
        className="py-1"
        contentContainerStyle={{ paddingHorizontal: 4 }}
      >
        {barChords.map((bc) => {
          const isActive = bc.bar === currentBar
          const isNoChord = bc.chord === 'N'
          return (
            <AnimatedPressable
              key={bc.bar}
              onPress={() => onChordTap?.(bc.eventIndex, bc.chord)}
              accessibilityRole="button"
              accessibilityLabel={`Chord ${isNoChord ? 'none' : formatChordDisplay(bc.chord)} at bar ${bc.bar + 1}`}
              className={`mx-0.5 items-center rounded-lg border px-2.5 py-1 ${
                isActive
                  ? 'border-amber-accent bg-amber-accent/20'
                  : 'border-wood-600/30 bg-wood-900/20'
              }`}
            >
              <Text
                className={`font-mono text-xs ${
                  isActive
                    ? 'font-sans-bold text-amber-accent'
                    : isNoChord
                      ? 'text-muted-brown/40'
                      : 'text-cream/80'
                }`}
              >
                {isNoChord ? '—' : formatChordDisplay(bc.chord)}
              </Text>
              <Text className="text-[9px] text-muted-brown/50">
                {bc.bar + 1}
              </Text>
            </AnimatedPressable>
          )
        })}
      </ScrollView>
    </View>
  )
}
