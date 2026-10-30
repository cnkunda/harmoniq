import { Text, View } from 'react-native'

import { colors } from '@/src/constants/colors'
import {
  confusionBarWidth,
  confusionLevel,
  confusionLevelLabel,
  type ConfusionLevel,
} from '@/src/session/transcriptionConfidence'
import type { InstrumentConfusionPerSection } from '@/src/types'

const CONFUSION_COLORS: Record<ConfusionLevel, string> = {
  low: colors.success,
  moderate: colors.amber.accent,
  high: colors.danger,
}

export function InstrumentConfusionBadge({ confusion }: { confusion: number | null }) {
  const level = confusionLevel(confusion)
  if (level === null) return null

  const color = CONFUSION_COLORS[level]
  const label = confusionLevelLabel(level)

  return (
    <View
      accessible
      accessibilityRole="text"
      accessibilityLabel={`Instrument confusion: ${label}`}
      className="flex-row items-center gap-2 rounded-lg border border-wood-600/35 bg-wood-800/40 px-3 py-2"
    >
      <View className="h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
      <Text className="font-sans text-xs text-cream">
        Instrument confusion: <Text className="font-sans-medium">{label}</Text>
      </Text>
    </View>
  )
}

export function PerSectionConfusionBars({
  sections,
  currentSectionIndex,
}: {
  sections: InstrumentConfusionPerSection[] | null | undefined
  currentSectionIndex: number
}) {
  if (!sections || sections.length === 0) return null

  return (
    <View
      testID="per-section-confusion-bars"
      className="rounded-lg border border-wood-600/35 bg-wood-800/40 px-3 py-2"
    >
      <Text className="font-sans-medium text-[10px] uppercase tracking-[0.12em] text-muted-brown mb-2">
        Confusion by section
      </Text>
      {sections.map((sec) => {
        const level = confusionLevel(sec.instrument_confusion)
        if (level === null) return null

        const color = CONFUSION_COLORS[level]
        const label = confusionLevelLabel(level)
        const width = confusionBarWidth(level)
        const isCurrent = sec.section_index === currentSectionIndex

        return (
          <View
            key={sec.section_index}
            accessible
            accessibilityRole="text"
            accessibilityLabel={`${sec.label}: ${label}`}
            className={`flex-row items-center py-1.5 ${isCurrent ? 'opacity-100' : 'opacity-60'}`}
          >
            <Text
              className={`font-sans text-[11px] ${isCurrent ? 'text-cream' : 'text-muted-brown'} w-20 shrink`}
              numberOfLines={1}
            >
              {sec.label}
            </Text>
            <View className="ml-2 h-2 flex-1 rounded-full bg-wood-700">
              <View
                className="h-full rounded-full"
                style={{
                  width: width ?? '0%',
                  backgroundColor: color,
                }}
              />
            </View>
            <Text className="ml-2 w-16 text-right font-mono text-[10px] text-muted-brown">
              {label}
            </Text>
          </View>
        )
      })}
    </View>
  )
}
