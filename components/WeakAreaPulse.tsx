import { X } from 'lucide-react-native'
import { useEffect, useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import type { SkillNodeRow } from '@/src/db/types'

function displayName(node: SkillNodeRow): string {
  return (node.label?.trim() || node.id.replace(/_/g, ' ')).trim() || node.id
}

export function WeakAreaPulse({
  node,
  onDismiss,
}: {
  node: SkillNodeRow
  onDismiss?: () => void
}) {
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    setDismissed(false)
  }, [node.id])

  if (dismissed) return null

  const name = displayName(node)
  const n = node.sessions_count

  return (
    <View className="mb-6 rounded-2xl border border-amber-accent/45 bg-amber-accent/10 px-4 py-3">
      <View className="flex-row items-start gap-2">
        <Text className="min-w-0 flex-1 font-sans text-sm leading-relaxed text-cream">
          You’ve scored under 50% on {name} across {n} recent checkpoints — today’s plan targets it directly.
        </Text>
        <AnimatedPressable
          haptic="light"
          onPress={() => {
            setDismissed(true)
            onDismiss?.()
          }}
          accessibilityRole="button"
          accessibilityLabel="Dismiss insight"
          className="rounded-full border border-wood-600/50 bg-wood-900/30 p-1.5"
        >
          <X color="#E8B86D" size={18} strokeWidth={2} />
        </AnimatedPressable>
      </View>
    </View>
  )
}
