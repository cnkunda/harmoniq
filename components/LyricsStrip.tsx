import { useEffect, useMemo, useRef, useState } from 'react'
import { ScrollView, Text, View } from 'react-native'

export type LyricWord = {
  word: string
  timeSec: number
}

type LyricsStripProps = {
  words: LyricWord[]
  playbackSec: number
  hideHeading?: boolean
}

function activeIndexForTime(words: LyricWord[], t: number): number {
  if (words.length === 0) return -1
  for (let i = words.length - 1; i >= 0; i -= 1) {
    if (t >= words[i].timeSec) return i
  }
  return -1
}

export function LyricsStrip({ words, playbackSec, hideHeading }: LyricsStripProps) {
  const activeIndex = useMemo(() => activeIndexForTime(words, playbackSec), [words, playbackSec])
  const scrollViewRef = useRef<ScrollView>(null)
  const [wordLayouts, setWordLayouts] = useState<{ [key: number]: { x: number; width: number } }>({})

  // Scroll to keep active word visible
  useEffect(() => {
    if (scrollViewRef.current && activeIndex >= 0 && wordLayouts[activeIndex]) {
      const { x, width } = wordLayouts[activeIndex]
      // Scroll to center the active word (with offset for padding)
      const scrollX = x - 60 // 60 is approximate center offset
      scrollViewRef.current.scrollTo({ x: Math.max(0, scrollX), animated: true })
    }
  }, [activeIndex, wordLayouts])

  const handleWordLayout = (index: number, event: any) => {
    const { x, width } = event.nativeEvent.layout
    setWordLayouts((prev) => ({
      ...prev,
      [index]: { x, width },
    }))
  }

  if (words.length === 0) {
    if (hideHeading) return null
    return (
      <Text className="mt-2 font-sans text-xs text-muted-light">
        Lyrics unavailable for this section.
      </Text>
    )
  }

  return (
    <View className={hideHeading ? "w-full" : "mt-2 w-full"}>
      {!hideHeading && (
        <Text className="mb-2 font-sans-medium text-xs uppercase tracking-wide text-amber-accent">
          Lyrics
        </Text>
      )}
      <ScrollView
        ref={scrollViewRef}
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: 16 }}
        scrollEventThrottle={16}
      >
        <View className="flex-row items-center gap-1.5 pb-1">
          {words.map((w, i) => (
            <Text
              key={`${i}-${w.timeSec}`}
              onLayout={(event) => handleWordLayout(i, event)}
              className={
                i === activeIndex
                  ? 'font-sans-medium text-base text-amber-accent'
                  : i < activeIndex
                  ? 'font-sans text-sm text-wood-900/60'
                  : 'font-sans text-sm text-muted-light'
              }
            >
              {w.word}
            </Text>
          ))}
        </View>
      </ScrollView>
    </View>
  )
}
