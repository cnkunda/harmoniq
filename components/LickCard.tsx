import { Text, View } from 'react-native'

import type { Lick } from '@/src/types'

export interface LickCardProps {
  lick?: Lick
  onPlay?: () => void
  onDrill?: () => void
}

/** Stub — full UI in DESIGN_SYSTEM.md */
export function LickCard(_props: LickCardProps) {
  return (
    <View className="rounded-lg border border-dashed border-wood-600 p-4">
      <Text className="font-mono text-amber-accent">LickCard</Text>
    </View>
  )
}
