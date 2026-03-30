import { Text, View } from 'react-native'

export interface PitchIndicatorProps {
  note?: string
  cents?: number
  isActive?: boolean
}

/** Stub — full UI in DESIGN_SYSTEM.md */
export function PitchIndicator(_props: PitchIndicatorProps) {
  return (
    <View className="rounded-lg border border-dashed border-wood-600 p-4">
      <Text className="font-mono text-amber-accent">PitchIndicator</Text>
    </View>
  )
}
