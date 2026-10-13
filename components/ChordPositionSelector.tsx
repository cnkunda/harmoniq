import { Text, View } from 'react-native'
import { ChevronLeft, ChevronRight } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'
import { getChordPositionCount } from '@/src/music/chordDbAdapter'

interface ChordPositionSelectorProps {
  chordSymbol: string
  currentIndex: number
  onPositionChange: (index: number) => void
}

export function ChordPositionSelector({
  chordSymbol,
  currentIndex,
  onPositionChange,
}: ChordPositionSelectorProps) {
  const total = getChordPositionCount(chordSymbol)

  if (total <= 1) return null

  const hasPrev = currentIndex > 0
  const hasNext = currentIndex < total - 1

  return (
    <View className="flex-row items-center gap-1">
      <AnimatedPressable
        onPress={() => onPositionChange(currentIndex - 1)}
        disabled={!hasPrev}
        className={`rounded p-0.5 ${hasPrev ? 'opacity-100' : 'opacity-30'}`}
        accessibilityLabel="Previous voicing"
      >
        <ChevronLeft size={12} color={colors.amber.accent} />
      </AnimatedPressable>

      <Text className="font-mono text-[10px] text-muted-brown">
        {currentIndex + 1}/{total}
      </Text>

      <AnimatedPressable
        onPress={() => onPositionChange(currentIndex + 1)}
        disabled={!hasNext}
        className={`rounded p-0.5 ${hasNext ? 'opacity-100' : 'opacity-30'}`}
        accessibilityLabel="Next voicing"
      >
        <ChevronRight size={12} color={colors.amber.accent} />
      </AnimatedPressable>
    </View>
  )
}
