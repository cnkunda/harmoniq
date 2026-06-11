import { Text, View } from 'react-native'

import type { InstrumentConfusionPerSection } from '@/src/types'

function confusionColor(confusion: number): string {
  if (confusion <= 0.15) return '#7A9B6D'
  if (confusion <= 0.30) return '#D4A574'
  return '#C17B5F'
}

function confusionLabel(confusion: number): string {
  if (confusion <= 0.15) return 'Low'
  if (confusion <= 0.30) return 'Moderate'
  return 'High'
}

export function InstrumentConfusionBadge({ confusion }: { confusion: number | null }) {
  if (confusion === null || confusion === undefined) return null

  const color = confusionColor(confusion)
  const label = confusionLabel(confusion)
  const pct = Math.round(confusion * 100)

  return (
    <View className="flex-row items-center gap-2 rounded-lg border border-wood-600/35 bg-wood-800/40 px-3 py-2">
      <View className="h-3 w-3 rounded-full" style={{ backgroundColor: color }} />
      <Text className="font-sans text-xs text-cream">
        Instrument confusion: <Text className="font-sans-medium">{pct}% ({label})</Text>
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
    <View className="rounded-lg border border-wood-600/35 bg-wood-800/40 px-3 py-2">
      <Text className="font-sans-medium text-[10px] uppercase tracking-[0.12em] text-muted-brown mb-2">
        Confusion by section
      </Text>
      {sections.map((sec) => {
        const color = confusionColor(sec.instrument_confusion)
        const pct = Math.round(sec.instrument_confusion * 100)
        const isCurrent = sec.section_index === currentSectionIndex

        return (
          <View
            key={sec.section_index}
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
                  width: `${Math.max(2, pct)}%`,
                  backgroundColor: color,
                }}
              />
            </View>
            <Text className="ml-2 w-10 text-right font-mono text-[10px] text-muted-brown">
              {pct}%
            </Text>
          </View>
        )
      })}
    </View>
  )
}
