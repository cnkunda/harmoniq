import React, { useMemo } from 'react'
import { View, Text } from 'react-native'
import { colors } from '@/src/constants/colors'

export interface ChordChartPreviewProps {
  chordEvents: Array<{ timestamp: number; chord: string; confidence: number }>
  /** Commit 152: audio duration in seconds — rendered as a header duration chip when known. */
  totalDuration?: number
  /** Commit 152: detected tempo — drives bar grouping (defaults to 120 BPM when unknown). */
  bpm?: number
  timeSignature?: { numerator: number; denominator: number }
  isPartial?: boolean
  /** Commit 152: chord inference still running — skeleton placeholder instead of empty text. */
  loading?: boolean
  style?: object
}

/** Format seconds as m:ss for the preview duration chip. */
function formatDuration(totalSeconds: number): string {
  const total = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

export function ChordChartPreview({
  chordEvents,
  totalDuration,
  bpm,
  timeSignature,
  isPartial = false,
  loading = false,
  style,
}: ChordChartPreviewProps) {
  const grouped = useMemo(() => {
    if (!chordEvents.length) return []
    const beatsPerBar = timeSignature?.numerator ?? 4
    const secondsPerBar = (60 / (bpm && bpm > 0 ? bpm : 120)) * beatsPerBar
    const groups: { bar: number; chords: typeof chordEvents }[] = []
    let currentBar = 0
    let currentGroup: typeof chordEvents = []

    for (const event of chordEvents) {
      const bar = Math.floor(event.timestamp / secondsPerBar)
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
  }, [chordEvents, timeSignature, bpm])

  const header = (
    <View className="mb-3 flex-row items-center gap-2">
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
      {typeof totalDuration === 'number' && totalDuration > 0 && (
        <Text className="text-xs font-mono" style={{ color: colors.muted.light }}>
          {formatDuration(totalDuration)}
        </Text>
      )}
    </View>
  )

  if (!chordEvents.length) {
    return (
      <View style={[{ padding: 12 }, style]}>
        {header}
        {loading ? (
          <View className="gap-1.5">
            <View className="h-7 w-2/5 rounded-md" style={{ backgroundColor: colors.wood[700] }} />
            <View className="h-7 w-3/5 rounded-md" style={{ backgroundColor: colors.wood[700] }} />
            <View className="h-7 w-1/3 rounded-md" style={{ backgroundColor: colors.wood[700] }} />
          </View>
        ) : (
          <Text className="text-sm font-sans text-muted-brown">No chord data yet</Text>
        )}
      </View>
    )
  }

  return (
    <View style={[{ padding: 12 }, style]}>
      {header}

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
        <Text className="mt-2 text-xs font-sans" style={{ color: colors.muted.light }}>
          Refining solo notation...
        </Text>
      )}
    </View>
  )
}
