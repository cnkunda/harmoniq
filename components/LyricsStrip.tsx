import { useMemo } from 'react'
import { ScrollView, Text, View } from 'react-native'

type LyricWord = {
  word: string
  timeSec: number
}

type LyricsStripProps = {
  words: LyricWord[]
  playbackSec: number
}

function activeIndexForTime(words: LyricWord[], t: number): number {
  if (words.length === 0) return -1
  for (let i = words.length - 1; i >= 0; i -= 1) {
    if (t >= words[i].timeSec) return i
  }
  return -1
}

export function LyricsStrip({ words, playbackSec }: LyricsStripProps) {
  const activeIndex = useMemo(() => activeIndexForTime(words, playbackSec), [words, playbackSec])

  if (words.length === 0) {
    return (
      <Text className="mt-2 font-sans text-xs text-muted-brown">
        Lyrics unavailable for this lesson section.
      </Text>
    )
  }

  return (
    <View className="mt-2">
      <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
        Lyrics
      </Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View className="flex-row flex-wrap items-center gap-2 pb-1">
          {words.map((w, i) => (
            <View
              key={`${i}-${w.timeSec}`}
              className={`rounded-full border px-2.5 py-1 ${
                i === activeIndex ? 'border-amber-accent bg-amber-accent/20' : 'border-wood-600/35 bg-cream-dark/40'
              }`}
            >
              <Text className={`font-sans text-xs ${i === activeIndex ? 'text-wood-900' : 'text-muted-brown'}`}>
                {w.word}
              </Text>
            </View>
          ))}
        </View>
      </ScrollView>
    </View>
  )
}
