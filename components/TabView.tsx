import { Text, View } from 'react-native'

export interface TabViewProps {
  isSkeleton?: boolean
  label?: string
}

/** Stub — AlphaTab integration in commits 21–22 (DESIGN_SYSTEM.md) */
export function TabView(_props: TabViewProps) {
  return (
    <View className="rounded-lg border border-dashed border-wood-600 p-4">
      <Text className="font-mono text-amber-accent">TabView</Text>
    </View>
  )
}
