import { useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from './AnimatedPressable'

export interface TheoryCardProps {
  chordName: string
  chordFunction: string
  romanNumeral: string
  rationale: string
  /** Optional tension indicator (0-1 scale) */
  tension?: number
}

/**
 * Expandable theory card showing chord function analysis and Claude rationale.
 * Displays below NoteDetailCard in the Study step.
 */
export function TheoryCard({
  chordName,
  chordFunction,
  romanNumeral,
  rationale,
  tension,
}: TheoryCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const toggleExpanded = () => setIsExpanded((prev) => !prev)

  // Determine tension color based on value
  const getTensionColor = () => {
    if (tension === undefined) return 'text-muted-light'
    if (tension < 0.3) return 'text-success'
    if (tension < 0.6) return 'text-amber-light'
    return 'text-danger'
  }

  const getTensionLabel = () => {
    if (tension === undefined) return null
    if (tension < 0.3) return 'Low tension'
    if (tension < 0.6) return 'Moderate tension'
    return 'High tension'
  }

  return (
    <View className="mt-3 rounded-2xl border border-wood-600 bg-wood-800 overflow-hidden">
      {/* Header - always visible */}
      <AnimatedPressable
        onPress={toggleExpanded}
        className="flex-row items-center justify-between p-4"
        accessibilityRole="button"
        accessibilityState={{ expanded: isExpanded }}
        accessibilityLabel={`Theory: ${chordName} functions as ${romanNumeral}. Tap to ${isExpanded ? 'collapse' : 'expand'} for explanation.`}
      >
        <View className="flex-row items-center gap-3 flex-1">
          <View className="h-8 w-8 rounded-full bg-wood-900 items-center justify-center border border-wood-600">
            <Text className="text-amber-light text-xs">🎵</Text>
          </View>
          <View className="flex-1">
            <View className="flex-row items-center gap-2">
              <Text className="font-serif text-lg text-cream">{chordName}</Text>
              <View className="rounded-full border border-amber-accent bg-wood-900 px-2 py-0.5">
                <Text className="font-sans-medium text-[10px] text-amber-light">{romanNumeral}</Text>
              </View>
            </View>
            <Text className="font-sans text-xs text-muted-light mt-0.5">{chordFunction}</Text>
          </View>
        </View>
        {getTensionLabel() ? (
          <View className="mr-2">
            <Text className={`font-sans-medium text-[10px] uppercase tracking-wide ${getTensionColor()}`}>
              {getTensionLabel()}
            </Text>
          </View>
        ) : null}
        <Text className="text-muted-light">{isExpanded ? '▼' : '▶'}</Text>
      </AnimatedPressable>

      {/* Expanded content - rationale */}
      {isExpanded && (
        <View className="border-t border-wood-700 bg-wood-900/50 p-4">
          <Text className="font-sans-medium text-[10px] uppercase tracking-wide text-amber-light mb-2">
            Theory insight
          </Text>
          <Text className="font-sans text-sm leading-relaxed text-cream">{rationale}</Text>
        </View>
      )}
    </View>
  )
}
