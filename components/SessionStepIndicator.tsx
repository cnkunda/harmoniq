import { usePathname } from 'expo-router'
import { View } from 'react-native'

import colors from '@/src/constants/colors'
import { SESSION_STEPS, sessionStepIndexFromPathname } from '@/src/constants/sessionFlow'

/** Minimal top dots — same tokens as design preview (amber-accent · wood-600). */
export function SessionStepIndicator() {
  const pathname = usePathname()
  const active = sessionStepIndexFromPathname(pathname)

  return (
    <View className="flex-row items-center justify-center gap-2 py-3">
      {SESSION_STEPS.map((step, i) => (
        <View
          key={step}
          className="rounded-full"
          style={{
            width: i === active ? 11 : 9,
            height: i === active ? 11 : 9,
            borderRadius: 99,
            backgroundColor: i <= active ? colors.amber.accent : colors.wood[600],
            opacity: i === active ? 1 : i < active ? 0.9 : 0.55,
          }}
        />
      ))}
    </View>
  )
}
