import { Text, View } from 'react-native'

export interface SessionStepperProps {
  currentStep?: number
}

/** Stub — full UI in DESIGN_SYSTEM.md */
export function SessionStepper(_props: SessionStepperProps) {
  return (
    <View className="rounded-lg border border-dashed border-wood-600 p-4">
      <Text className="font-mono text-amber-accent">SessionStepper</Text>
    </View>
  )
}
