import { ActivityIndicator, Text, View } from 'react-native'
import { Music, Play, Plus } from 'lucide-react-native'

import { AnimatedPressable } from '@/components/AnimatedPressable'
import { colors } from '@/src/constants/colors'

export interface SongPickerItem {
  jobId: string
  title: string
  /** Last-played / progress line shown under the title. */
  meta: string
  /** Short right-side metadata, e.g. section count. */
  rightMeta: string
}

export interface SongPickerCardProps {
  songs: readonly SongPickerItem[]
  selectedJobId: string | null
  focusHint: string | null
  busy: boolean
  errorText: string | null
  onSelect: (jobId: string) => void
  onStart: () => void
  onAddSong: () => void
}

export function SongPickerCard({
  songs,
  selectedJobId,
  focusHint,
  busy,
  errorText,
  onSelect,
  onStart,
  onAddSong,
}: SongPickerCardProps) {
  const selectedSong = songs.find((song) => song.jobId === selectedJobId) ?? null

  return (
    <View>
      <View className="mb-6">
        <Text className="font-serif text-2xl text-cream">Pick a song</Text>
        <Text className="mt-1 font-sans text-sm text-amber-light/80">Recent songs from your library</Text>
        {focusHint ? (
          <Text className="mt-2 font-sans text-xs leading-5 text-muted-brown">{focusHint}</Text>
        ) : null}
      </View>

      <View className="gap-2">
        {songs.map((song) => {
          const selected = song.jobId === selectedJobId
          return (
            <AnimatedPressable
              key={song.jobId}
              onPress={() => onSelect(song.jobId)}
              haptic="light"
              accessibilityRole="button"
              accessibilityState={{ selected }}
              accessibilityLabel={`Select ${song.title}`}
              className={`min-h-[68px] flex-row items-center gap-4 rounded-2xl border px-4 py-3 ${
                selected ? 'border-wood-600/70 bg-amber-accent/10' : 'border-transparent'
              }`}
            >
              <View
                className={`h-9 w-9 flex-none items-center justify-center rounded-full border ${
                  selected
                    ? 'border-amber-accent bg-amber-accent'
                    : 'border-wood-600/60 bg-wood-900/40'
                }`}
              >
                <Music color={selected ? colors.wood[900] : colors.cream} size={16} strokeWidth={2} />
              </View>
              <View className="flex-1">
                <Text className="font-sans-medium text-[17px] text-cream" numberOfLines={1}>
                  {song.title}
                </Text>
                <Text className="font-sans text-sm text-muted-brown" numberOfLines={1}>
                  {song.meta}
                </Text>
              </View>
              <Text className="font-sans text-sm text-cream/80">{song.rightMeta}</Text>
            </AnimatedPressable>
          )
        })}

        <AnimatedPressable
          onPress={onAddSong}
          haptic="light"
          accessibilityRole="button"
          accessibilityLabel="Add a new song"
          className="min-h-[60px] flex-row items-center gap-4 rounded-2xl border border-dashed border-wood-600/50 px-4 py-3"
        >
          <View className="h-9 w-9 flex-none items-center justify-center rounded-full border border-wood-600/60 bg-wood-900/40">
            <Plus color={colors.amber.light} size={18} strokeWidth={2} />
          </View>
          <View className="flex-1">
            <Text className="font-sans-medium text-sm text-cream">Add a new song</Text>
            <Text className="font-sans text-xs text-muted-brown">Search or import</Text>
          </View>
        </AnimatedPressable>
      </View>

      {errorText ? <Text className="mt-3 font-sans text-sm text-danger">{errorText}</Text> : null}

      <AnimatedPressable
        onPress={onStart}
        disabled={busy || selectedSong == null}
        haptic="medium"
        accessibilityRole="button"
        accessibilityLabel={selectedSong ? `Practice ${selectedSong.title}` : 'Choose a song to practice'}
        accessibilityState={{ disabled: busy || selectedSong == null, busy }}
        className={`mt-6 min-h-[60px] w-full flex-row items-center justify-center gap-2 rounded-2xl bg-amber-accent px-6 py-4 shadow-md ${
          busy || selectedSong == null ? 'opacity-70' : 'active:opacity-95'
        }`}
      >
        {busy ? (
          <ActivityIndicator color={colors.wood[900]} size="small" />
        ) : (
          <>
            <Play color={colors.wood[900]} size={20} fill={colors.wood[900]} strokeWidth={0} />
            <Text className="font-sans-medium text-base text-wood-900">
              {selectedSong ? `Practice ${selectedSong.title}` : 'Choose a song'}
            </Text>
          </>
        )}
      </AnimatedPressable>
      <Text className="mt-3 text-center font-sans text-xs text-muted-brown">
        Listen → Study → Slow → Play → Review
      </Text>
    </View>
  )
}
