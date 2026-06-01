import { View, Text } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { ChordDiagram } from '@/components/ChordDiagram'
import {
  CHOICE_CHIP_BASE,
  CHOICE_CHIP_OFF,
  CHOICE_CHIP_ON,
  SECTION_EYEBROW_CLASS,
} from '@/src/constants/uiTokens'
import { chordToFretboardCells, type VoicingMode } from '@/src/music/chordVoicing'

const CAGED_SHAPES = ['E-shape', 'A-shape', 'D-shape', 'C-shape', 'G-shape'] as const

type VoicingSelectorProps = {
  chordSymbol: string
  currentShape: string | null
  onSelect: (shape: string) => void
}

/**
 * Chip-based CAGED voicing shape selector.
 * Each chip shows a mini chord diagram previewing the shape.
 */
export function VoicingSelector({ chordSymbol, currentShape, onSelect }: VoicingSelectorProps) {
  if (!chordSymbol || chordSymbol === 'N') return null

  return (
    <View>
      <Text className={SECTION_EYEBROW_CLASS}>Voicing Shape</Text>
      <View className="mt-2 flex-row flex-wrap gap-2">
        {CAGED_SHAPES.map((shape) => {
          const isActive = currentShape === shape
          return (
            <AnimatedPressable
              key={shape}
              onPress={() => onSelect(shape)}
              className={`${CHOICE_CHIP_BASE} ${isActive ? CHOICE_CHIP_ON : CHOICE_CHIP_OFF} items-center px-3 py-2`}
            >
              <Text
                className={`font-sans-medium text-xs ${isActive ? 'text-wood-900' : 'text-muted-brown'}`}
              >
                {shape}
              </Text>
            </AnimatedPressable>
          )
        })}
      </View>
    </View>
  )
}
