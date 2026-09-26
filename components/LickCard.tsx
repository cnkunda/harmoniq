import { Text, View } from 'react-native'
import { Play, Tag } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'
import type { Lick } from '@/src/types'

export interface LickCardProps {
  lick: Lick
  onPlay?: () => void
  onDrill?: () => void
}

export function LickCard({ lick, onPlay, onDrill }: LickCardProps) {
  return (
    <View className="overflow-hidden rounded-xl border border-wood-600/50 bg-wood-700/80 p-5">
      <View className="mb-3 flex-row items-start justify-between">
        <View className="mr-3 flex-1">
          <Text className="mb-0.5 font-serif text-lg text-cream">{lick.song_title}</Text>
          <Text className="font-sans text-sm text-muted-brown">{lick.artist}</Text>
        </View>
        {onPlay && (
          <AnimatedPressable
            haptic="light"
            onPress={onPlay}
            className="h-10 w-10 items-center justify-center rounded-full border border-wood-600 bg-wood-800"
          >
            <Play
              color={colors.amber.accent}
              size={16}
              style={{ marginLeft: 2 }}
            />
          </AnimatedPressable>
        )}
      </View>

      <View className="mb-3 flex-row flex-wrap gap-2">
        <View className="rounded border border-wood-700 bg-wood-800 px-2 py-1">
          <Text className="font-sans text-xs text-amber-light/80">{lick.key}</Text>
        </View>
        <View className="rounded border border-wood-700 bg-wood-800 px-2 py-1">
          <Text className="font-sans text-xs text-cream/70">{lick.position}</Text>
        </View>
      </View>

      <View className="mb-3 flex-row flex-wrap gap-2">
        {lick.technique_tags.map((tag) => (
          <View key={tag} className="flex-row items-center gap-1">
            <Tag color={colors.muted.brown} size={10} />
            <Text className="font-sans text-[10px] uppercase tracking-wider text-muted-brown">
              {tag}
            </Text>
          </View>
        ))}
      </View>

      <View className="border-t border-wood-700/50 pt-3">
        <Text className="font-sans text-sm italic leading-relaxed text-cream/80">
          &ldquo;{lick.coach_oneliner}&rdquo;
        </Text>
      </View>

      {onDrill && (
        <AnimatedPressable
          haptic="light"
          onPress={onDrill}
          className="mt-3 items-center rounded-lg border border-wood-600 bg-wood-700 py-2"
        >
          <Text className="font-sans-medium text-xs uppercase tracking-wider text-amber-light">
            Drill this
          </Text>
        </AnimatedPressable>
      )}
    </View>
  )
}
