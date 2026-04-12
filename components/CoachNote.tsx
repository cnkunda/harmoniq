import { MessageSquare } from 'lucide-react-native'
import { Text, View } from 'react-native'

import colors from '@/src/constants/colors'

export interface CoachNoteProps {
  text?: string
  className?: string
}

/** Coach bubble — aligned with DESIGN_SYSTEM.md. */
export function CoachNote({ text = '', className = '' }: CoachNoteProps) {
  return (
    <View
      className={`relative overflow-hidden rounded-xl border border-wood-600/50 bg-wood-700/80 p-5 ${className}`}
    >
      <View className="absolute bottom-0 left-0 top-0 w-1 bg-amber-accent/40" />
      <View className="flex-row items-start gap-4">
        <View className="mt-1 h-8 w-8 items-center justify-center rounded-full border border-wood-600 bg-wood-800">
          <MessageSquare color={colors.amber.accent} size={16} strokeWidth={1.5} />
        </View>
        <Text className="flex-1 font-sans text-[15px] leading-relaxed text-cream/90">{text}</Text>
      </View>
    </View>
  )
}
