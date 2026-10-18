import { Text, View } from 'react-native'

import { colors } from '@/src/constants/colors'
import { formatHarmonyPercents } from '@/src/music/soloHarmony'
import type { HarmonizedSoloNotes } from '@/src/types/soloHarmony'

export function SoloHarmonySummaryCard({ harmonized }: { harmonized: HarmonizedSoloNotes }) {
  const percents = formatHarmonyPercents(harmonized)
  const rows: Array<{ label: string; value: number; color: string }> = [
    { label: 'Chord tones', value: percents.chordTone, color: colors.success },
    { label: 'Tensions', value: percents.tension, color: colors.amber.accent },
    { label: 'Chromatic / outside', value: percents.chromatic, color: colors.danger },
  ]

  return (
    <View className="mt-3 rounded-xl border border-wood-600/35 bg-wood-800/40 px-3 py-2">
      <Text className="font-sans-medium text-[10px] uppercase tracking-[0.12em] text-muted-brown mb-2">
        Reference solo note roles
      </Text>
      <View className="gap-2">
        {rows.map((row) => (
          <View key={row.label} className="flex-row items-center justify-between">
            <View className="flex-row items-center gap-1.5">
              <View className="h-2 w-2 rounded-full" style={{ backgroundColor: row.color }} />
              <Text className="font-sans-medium text-sm text-cream">{row.label}</Text>
            </View>
            <Text className="font-sans text-sm" style={{ color: row.color }}>
              {row.value}%
            </Text>
          </View>
        ))}
      </View>
      <Text className="mt-2 font-sans text-[11px] text-muted-brown">
        Note roles in the reference solo — from the transcription, not your take.
      </Text>
    </View>
  )
}
