import { ArrowRight, Music } from 'lucide-react-native'
import { Text, View } from 'react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import colors from '@/src/constants/colors'
import type { DiscoverySuggestion } from '@/src/types'

export interface DiscoveryCardProps {
  suggestion: DiscoverySuggestion
  onAnalyze?: () => void
}

/**
 * Discovery card for song recommendations (commit 91).
 * Displays a song suggestion with context and one-tap deep-link to analyze.
 */
export function DiscoveryCard({ suggestion, onAnalyze }: DiscoveryCardProps) {
  return (
    <AnimatedPressable
      onPress={onAnalyze}
      className="mx-4 mb-4 rounded-xl border border-wood-600/30 bg-wood-800/60 p-4"
    >
      <View className="flex-row items-start gap-3">
        <View className="h-12 w-12 items-center justify-center rounded-full border border-wood-600 bg-wood-900">
          <Music color={colors.amber.accent} size={20} strokeWidth={1.5} />
        </View>
        <View className="flex-1">
          <Text className="font-sans text-[16px] font-semibold text-cream">{suggestion.song_title || 'Unknown Song'}</Text>
          <Text className="font-sans text-[14px] text-cream/85">{suggestion.artist || 'Unknown Artist'}</Text>
          
          <View className="mt-2 flex-row flex-wrap gap-2">
            {suggestion.key && (
              <View className="rounded-full bg-wood-700 px-2 py-0.5">
                <Text className="font-sans text-[11px] font-medium text-cream/90">{suggestion.key}</Text>
              </View>
            )}
            {suggestion.style_label && (
              <View className="rounded-full bg-wood-700 px-2 py-0.5">
                <Text className="font-sans text-[11px] font-medium text-cream/90">{suggestion.style_label}</Text>
              </View>
            )}
            {suggestion.tempo && (
              <View className="rounded-full bg-wood-700 px-2 py-0.5">
                <Text className="font-sans text-[11px] font-medium text-cream/90">{Math.round(suggestion.tempo)} BPM</Text>
              </View>
            )}
          </View>
          
          <View className="mt-3 rounded-lg bg-wood-900/50 p-3">
            <Text className="font-sans text-[13px] leading-relaxed text-cream/80">{suggestion.reasonLabel}</Text>
          </View>
          
          <View className="mt-3 flex-row items-center justify-between">
            <Text className="font-sans text-[12px] font-medium text-amber-light">Focus: {suggestion.techniqueFocus}</Text>
            <View className="flex-row items-center gap-1">
              <Text className="font-sans text-[12px] font-medium text-cream/90">Analyze</Text>
              <ArrowRight color={colors.muted.light} size={14} strokeWidth={2} />
            </View>
          </View>
        </View>
      </View>
    </AnimatedPressable>
  )
}
