import React, { useMemo } from 'react'
import { View, Text } from 'react-native'
import colors from '@/src/constants/colors'

export interface ChordChartPreviewProps {
  chordEvents: Array<{ timestamp: number; chord: string; confidence: number }>
  totalDuration: number
  timeSignature?: { numerator: number; denominator: number }
  isPartial?: boolean
  style?: object
}

export function ChordChartPreview({
  chordEvents,
  totalDuration,
  timeSignature,
  isPartial = false,
  style,
}: ChordChartPreviewProps) {
  const grouped = useMemo(() => {
    if (!chordEvents.length) return []
    const beatsPerBar = timeSignature?.numerator ?? 4
    const groups: { bar: number; chords: typeof chordEvents }[] = []
    let currentBar = 0
    let currentGroup: typeof chordEvents = []

    for (const event of chordEvents) {
      const bar = Math.floor(event.timestamp / ((60 / 120) * beatsPerBar))
      if (bar !== currentBar && currentGroup.length > 0) {
        groups.push({ bar: currentBar, chords: currentGroup })
        currentGroup = []
        currentBar = bar
      }
      currentGroup.push(event)
    }
    if (currentGroup.length > 0) {
      groups.push({ bar: currentBar, chords: currentGroup })
    }
    return groups
  }, [chordEvents, timeSignature])

  if (!chordEvents.length) {
    return (
      <View style={[{ padding: 12 }, style]}>
        <Text className="text-sm font-sans text-muted-light">No chord data yet</Text>
      </View>
    )
  }

  return (
    <View style={[{ padding: 12 }, style]}>
      <View className="flex-row items-center gap-2 mb-3">
        <Text className="text-sm font-serif" style={{ color: colors.cream }}>
          Chord Chart
        </Text>
        {isPartial && (
          <View className="rounded-full px-2 py-0.5" style={{ backgroundColor: colors.wood[600] }}>
            <Text className="text-xs font-sans" style={{ color: colors.amber.accent }}>
              Partial
            </Text>
          </View>
        )}
      </View>

      <View className="flex-row flex-wrap gap-1">
        {grouped.map((group) => (
          <View key={group.bar} className="flex-row items-center gap-1">
            {group.chords.map((event, i) => (
              <View
                key={`${group.bar}-${i}`}
                className="rounded-md px-2 py-1"
                style={{ backgroundColor: colors.wood[700] }}
              >
                <Text className="text-xs font-mono" style={{ color: colors.cream }}>
                  {event.chord}
                </Text>
              </View>
            ))}
          </View>
        ))}
      </View>

      {isPartial && (
        <Text className="text-xs font-sans mt-2" style={{ color: colors.muted.light }}>
          Refining solo notation...
        </Text>
      )}
    </View>
  )
}
