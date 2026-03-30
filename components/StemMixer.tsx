import { Text, View } from 'react-native'

type StemKey = 'guitar' | 'bass' | 'drums' | 'vocals'

export interface StemMixerProps {
  onMuteChange?: (active: Record<StemKey, boolean>) => void
  defaults?: Partial<Record<StemKey, boolean>>
  className?: string
}

/** Stub — full UI in DESIGN_SYSTEM.md */
export function StemMixer(_props: StemMixerProps) {
  return (
    <View className="rounded-lg border border-dashed border-wood-600 p-4">
      <Text className="font-mono text-amber-accent">StemMixer</Text>
    </View>
  )
}
