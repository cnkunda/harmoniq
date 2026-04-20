import { Text, View } from 'react-native'

type Props = {
  children: string
  className?: string
}

/** Guided demo tour hint — amber border, sits below SessionStepScreen title/subtitle. */
export function DemoTourCallout({ children, className }: Props) {
  return (
    <View className={`mb-4 rounded-xl border border-amber-accent/45 bg-amber-accent/10 px-4 py-3 ${className ?? ''}`}>
      <Text className="font-sans text-sm leading-relaxed text-wood-900">{children}</Text>
    </View>
  )
}
