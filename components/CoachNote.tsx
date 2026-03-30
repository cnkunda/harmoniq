import { Text, View } from 'react-native'

export interface CoachNoteProps {
  text?: string
  className?: string
}

/** Stub — full UI in DESIGN_SYSTEM.md */
export function CoachNote(_props: CoachNoteProps) {
  return (
    <View className="rounded-lg border border-dashed border-wood-600 p-4">
      <Text className="font-mono text-amber-accent">CoachNote</Text>
    </View>
  )
}
