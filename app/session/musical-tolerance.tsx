import { useRouter } from 'expo-router'
import { Crosshair, Feather } from 'lucide-react-native'
import { useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'
import { setAppPref } from '@/src/db/client'
import { PREF_MUSICAL_TOLERANCE_MODE } from '@/src/db/schema'
import type { MusicalToleranceMode } from '@/src/types'

const TOLERANCE_ICON = {
  expressive: Feather,
  technique: Crosshair,
} as const

export default function MusicalToleranceScreen() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)

  const commitAndGo = async (mode: MusicalToleranceMode): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      await setAppPref(PREF_MUSICAL_TOLERANCE_MODE, mode)
      console.info('[musical-tolerance] saved', mode)
      router.replace('/session/listen')
    } finally {
      setBusy(false)
    }
  }

  const options: Array<{
    id: MusicalToleranceMode
    label: string
    subtitle: string
    tolerance: string
  }> = [
    {
      id: 'expressive',
      label: 'Expressive',
      subtitle: 'Lenient timing for musical feel',
      tolerance: '±75ms timing tolerance',
    },
    {
      id: 'technique',
      label: 'Technique',
      subtitle: 'Strict timing for precision practice',
      tolerance: '±20ms timing tolerance',
    },
  ]

  return (
    <View className="flex-1 bg-transparent px-6 pt-8">
      <View className="mx-auto w-full max-w-xl rounded-2xl border border-wood-600/40 bg-wood-800/60 p-6">
        <Text className="font-serif text-3xl text-cream">Choose your scoring mode</Text>
        <Text className="mt-2 font-sans text-sm leading-5 text-muted-brown">
          How should we evaluate your timing? Expressive mode allows for musical feel, while Technique mode enforces precision.
        </Text>
        <View className="mt-6 gap-3">
          {options.map((opt) => {
            const Icon = TOLERANCE_ICON[opt.id]
            return (
              <AnimatedPressable
                key={opt.id}
                haptic="light"
                disabled={busy}
                onPress={() => void commitAndGo(opt.id)}
                className="rounded-xl border border-wood-600/45 bg-wood-700/40 px-4 py-3 active:opacity-90 disabled:opacity-50"
                accessibilityRole="button"
                accessibilityLabel={`Select mode ${opt.label}`}
              >
                <View className="flex-row items-center gap-2">
                  <Icon color={colors.amber.accent} size={18} strokeWidth={1.5} />
                  <Text className="font-sans-medium text-base text-cream">{opt.label}</Text>
                </View>
                <Text className="mt-1 font-sans text-xs leading-5 text-muted-brown">{opt.subtitle}</Text>
                <Text className="mt-2 font-sans text-[11px] text-amber-accent/80">{opt.tolerance}</Text>
              </AnimatedPressable>
            )
          })}
        </View>
        <AnimatedPressable
          disabled={busy}
          onPress={() => void commitAndGo('technique')}
          className="mt-4 rounded-lg border border-dashed border-wood-600/40 bg-wood-700/20 px-4 py-3 active:opacity-90 disabled:opacity-50"
          accessibilityRole="button"
          accessibilityLabel="Skip and use default technique mode"
        >
          <Text className="font-sans text-xs text-muted-brown">Skip (default: Technique)</Text>
        </AnimatedPressable>
      </View>
    </View>
  )
}
