import { useRouter } from 'expo-router'
import { Flame, Moon, Target, Wind } from 'lucide-react-native'
import { useEffect, useMemo, useState } from 'react'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'
import { getAppPref, setAppPref } from '@/src/db/client'
import { sessionEntryHref } from '@/src/constants/sessionFlow'
import {
  PREF_MOOD_CHECK_LAST_MOOD,
  PREF_MOOD_CHECK_LAST_SHOWN_DAY,
} from '@/src/db/schema'
import { useSessionPrefsStore } from '@/src/stores/sessionPrefsStore'
import type { MoodState } from '@/src/types'

const MOOD_ICON = {
  focused: Target,
  loose: Wind,
  tired: Moon,
  on_fire: Flame,
} as const

function todayKey(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export default function MoodCheckScreen() {
  const router = useRouter()
  const skipTune = useSessionPrefsStore((s) => s.skipTuneStep)
  const [busy, setBusy] = useState(false)
  const day = useMemo(() => todayKey(), [])

  useEffect(() => {
    void setAppPref(PREF_MOOD_CHECK_LAST_SHOWN_DAY, day)
  }, [day])

  const commitAndGo = async (mood: MoodState | null): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      const nextMood = mood ?? ''
      const prev = (await getAppPref(PREF_MOOD_CHECK_LAST_MOOD)) ?? ''
      await Promise.all([
        setAppPref(PREF_MOOD_CHECK_LAST_SHOWN_DAY, day),
        setAppPref(PREF_MOOD_CHECK_LAST_MOOD, nextMood),
      ])
      console.info('[mood-check] saved', nextMood || 'skip', 'previous=', prev || 'none')
      router.replace(sessionEntryHref(skipTune))
    } finally {
      setBusy(false)
    }
  }

  const options: Array<{ id: MoodState; label: string; subtitle: string }> = [
    { id: 'focused', label: 'Focused', subtitle: 'Structured, detail-first reps.' },
    { id: 'loose', label: 'Loose', subtitle: 'Flow over perfection today.' },
    { id: 'tired', label: 'Tired', subtitle: 'Lower intensity, shorter blocks.' },
    { id: 'on_fire', label: 'On Fire', subtitle: 'Push pace and energy.' },
  ]

  return (
    <View className="flex-1 bg-transparent px-6 pt-8">
      <View className="mx-auto w-full max-w-xl rounded-2xl border border-wood-600/40 bg-wood-800/60 p-6">
        <Text className="font-serif text-3xl text-cream">How are you feeling today?</Text>
        <Text className="mt-2 font-sans text-sm leading-5 text-muted-brown">
          We tune your session intensity, tempo defaults, and coach tone to match your state.
        </Text>
        <View className="mt-6 gap-3">
          {options.map((opt) => {
            const Icon = MOOD_ICON[opt.id]
            return (
              <AnimatedPressable
                key={opt.id}
                haptic="light"
                disabled={busy}
                onPress={() => void commitAndGo(opt.id)}
                className="rounded-xl border border-wood-600/45 bg-wood-700/40 px-4 py-3 active:opacity-90 disabled:opacity-50"
                accessibilityRole="button"
                accessibilityLabel={`Select mood ${opt.label}`}
              >
                <View className="flex-row items-center gap-2">
                  <Icon color={colors.amber.accent} size={18} strokeWidth={1.5} />
                  <Text className="font-sans-medium text-base text-cream">{opt.label}</Text>
                </View>
                <Text className="mt-1 font-sans text-xs leading-5 text-muted-brown">{opt.subtitle}</Text>
              </AnimatedPressable>
            )
          })}
        </View>
        <AnimatedPressable
          haptic="light"
          disabled={busy}
          onPress={() => void commitAndGo(null)}
          className="mt-5 self-start rounded-lg border border-wood-600/40 bg-wood-700/30 px-4 py-2.5 disabled:opacity-50"
          accessibilityRole="button"
          accessibilityLabel="Skip mood check"
        >
          <Text className="font-sans-medium text-sm text-cream">Skip</Text>
        </AnimatedPressable>
      </View>
    </View>
  )
}
