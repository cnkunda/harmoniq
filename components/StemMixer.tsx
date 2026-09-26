import { useState } from 'react'
import { Text, View } from 'react-native'
import { Drum, Guitar, Mic, Music2 } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'

type StemKey = 'guitar' | 'bass' | 'drums' | 'vocals'

export interface StemMixerProps {
  onMuteChange?: (active: Record<StemKey, boolean>) => void
  defaults?: Partial<Record<StemKey, boolean>>
  className?: string
}

const STEMS: { key: StemKey; label: string; Icon: typeof Guitar }[] = [
  { key: 'guitar', label: 'Guitar', Icon: Guitar },
  { key: 'bass', label: 'Bass', Icon: Music2 },
  { key: 'drums', label: 'Drums', Icon: Drum },
  { key: 'vocals', label: 'Vocals', Icon: Mic },
]

export function StemMixer({ onMuteChange, defaults, className = '' }: StemMixerProps) {
  const [active, setActive] = useState<Record<StemKey, boolean>>({
    guitar: true,
    bass: false,
    drums: false,
    vocals: false,
    ...defaults,
  })

  const toggle = (key: StemKey) => {
    const next = { ...active, [key]: !active[key] }
    setActive(next)
    onMuteChange?.(next)
  }

  return (
    <View className={`rounded-xl border border-wood-700/50 bg-wood-800/60 p-4 ${className}`}>
      <Text className="mb-3 font-sans-medium text-xs uppercase tracking-wider text-muted-brown">
        Stem Mixer
      </Text>
      <View className="flex-row gap-2">
        {STEMS.map(({ key, label, Icon }) => {
          const isActive = active[key]
          return (
            <AnimatedPressable
              key={key}
              haptic="light"
              onPress={() => toggle(key)}
              className={`flex-1 items-center rounded-lg border py-3 ${
                isActive
                  ? 'border-amber-accent/40 bg-wood-700'
                  : 'border-transparent bg-wood-900/50'
              }`}
            >
              <Icon
                color={isActive ? colors.amber.light : colors.muted.brown}
                size={20}
                strokeWidth={2}
              />
              <Text
                className={`mt-1.5 text-[10px] font-sans-medium ${
                  isActive ? 'text-amber-light' : 'text-muted-brown'
                }`}
              >
                {label}
              </Text>
            </AnimatedPressable>
          )
        })}
      </View>
    </View>
  )
}
