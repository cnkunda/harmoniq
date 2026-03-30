import { Text, View } from 'react-native'

import type { SkillNode } from '@/src/types'

export interface SkillGraphProps {
  nodes?: SkillNode[]
  size?: number
}

/** Stub — full UI in DESIGN_SYSTEM.md */
export function SkillGraph(_props: SkillGraphProps) {
  return (
    <View className="rounded-lg border border-dashed border-wood-600 p-4">
      <Text className="font-mono text-amber-accent">SkillGraph</Text>
    </View>
  )
}
